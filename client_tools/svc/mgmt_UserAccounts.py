import win32api
import win32con
import win32security
import win32process
import win32ts
import win32profile
import ctypes
import win32netcon
import ntsecuritycon
import win32net
import wmi
import traceback
import shutil
import random

from winsys import accounts
from color import p
import util

from mgmt_RegistrySettings import RegistrySettings

class UserAccounts:

    # All student accounts get added to this group
    STUDENTS_GROUP = "OPEStudents"
    
    GROUP_EVERYONE = None
    GROUP_ADMINISTRATORS = None
    CURRENT_USER = None
    SYSTEM_USER = None

    DISABLE_ACCOUNT_FLAGS = win32netcon.UF_SCRIPT | win32netcon.UF_ACCOUNTDISABLE | \
            win32netcon.UF_PASSWD_CANT_CHANGE | win32netcon.UF_DONT_EXPIRE_PASSWD
    ENABLE_ACCOUNT_FLAGS = win32netcon.UF_NORMAL_ACCOUNT | win32netcon.UF_PASSWD_CANT_CHANGE | \
            win32netcon.UF_DONT_EXPIRE_PASSWD | win32netcon.UF_SCRIPT

    #service_account = accounts.principal (accounts.WELL_KNOWN_SID.Service)
    #local_admin = accounts.principal ("Administrator")
    #domain_users = accounts.principal (r"DOMAIN\Domain Users")

    # Invalid session ID for WTS
    WTS_INVALID_SESSION_ID = 0xffffffff
    #TS State Enum
    WTSActive = 0
    WTSConnected = 1
    WTSConnectQuery = 2
    WTSShadow = 3
    WTSDisconnected = 4
    WTSIdle = 5
    WTSListen = 6
    WTSReset = 7
    WTSDown = 8
    WTSInit = 9


    @staticmethod
    def get_current_user():
        return win32api.GetUserName()
    
    @staticmethod
    def get_active_user_name():
        user_name = ""
        user_token = UserAccounts.get_active_user_token()
        
        if user_token is None:
            # Unable to pull active user, no one logged in?
            return ""

        # Translate to SID
        sidObj, intVal = win32security.GetTokenInformation(user_token, win32security.TokenUser)
        if sidObj:
            accountName, domainName, accountTypeInt = win32security.LookupAccountSid(".", sidObj)
            #p("}}gnRunning As: " + accountName + "}}xx", debug_level=2)
            user_name = accountName
        else:
            p("}}rnUnable to get User Token! }}xx", debug_level=1)
            return ""
        #p("}}gnFound User Token: " + str(user_token) + "}}xx", debug_level=5)
        user_token.close()

        return user_name
    
    @staticmethod
    def get_active_user_token():
        # Figure out the active user token we need to use to run the app as
        ret = None

        # Get the current user name
        user_name = win32api.GetUserName()

        if user_name != "SYSTEM":
            # Running as a logged in user, get the current users token
            current_process = win32process.GetCurrentProcess()
            token = win32security.OpenProcessToken(current_process,
                win32con.MAXIMUM_ALLOWED)
                # win32con.TOKEN_ADJUST_PRIVILEGES | win32con.TOKEN_QUERY)  #

            ret = token

            return ret

        #if user_name == "SYSTEM":
        #    p("}}gnStarted by SYSTEM user (OPEService) - trying to switch user identity}}xx")

        # Get a list of Terminal Service sessions and see which one is active
        active_session = UserAccounts.WTS_INVALID_SESSION_ID
        station_name = ""
        sessions = win32ts.WTSEnumerateSessions(None, 1, 0)
        
        for session in sessions:
            if session['State'] == UserAccounts.WTSActive:
                # Found the active session
                active_session = session['SessionId']
                station_name = session["WinStationName"]

        # If we didn't find one, try this way
        if active_session == UserAccounts.WTS_INVALID_SESSION_ID:
            active_session = win32ts.WTSGetActiveConsoleSessionId()
        if active_session == UserAccounts.WTS_INVALID_SESSION_ID:
                # User not logged in right now? or lock screen up?
                p("}}gnNo console user or desktop locked}}xx", log_level=1)
                return ret
            
        # Get the current console session
        #p("Got Console: " + str(active_session), debug_level=5)

        # Login to the terminal service to get the user token for the console id so we can impersonate it
        try:
            #svr = win32ts.WTSOpenServer(".")
            #win32ts.WTSCloseServer(svr)
            user_token = win32ts.WTSQueryUserToken(active_session)

             # Copy the token so we can modify it
            user_token_copy = win32security.DuplicateTokenEx(user_token,
                                                    win32security.SecurityImpersonation,
                                                    win32security.TOKEN_ALL_ACCESS,
                                                    win32security.TokenPrimary)

            ret = user_token_copy
            user_token.close()
        except Exception as ex:
            p("}}rnUnknown Error - trying to get WTS UserToken\n" + str(ex) + "}}xx", debug_level=1)
            return ret
        
        #p("User Token Found " + str(user_token_copy), debug_level=5)

        return ret

    @staticmethod
    def get_student_login_sessions():
        # Get a list of students that are logged in
        ret = []

        # Get the current user name
        curr_user = win32api.GetUserName()
        if UserAccounts.is_user_in_group(curr_user, "OPEStudents"):
            ret.append(curr_user)

        # Get the list of users from WTS
        wts_sessions = []
        sessions = win32ts.WTSEnumerateSessions(None, 1, 0)
        
        for session in sessions:
            # Ignore listen status(no user for that), all others query
            if session['State'] == UserAccounts.WTSActive or \
                session['State'] == UserAccounts.WTSDisconnected or \
                session['State'] == UserAccounts.WTSConnected:
                # Found the active session
                #active_session = session['SessionId']
                #station_name = session["WinStationName"]
                wts_sessions.append(session['SessionId'])
        
        # Get the console session (duplicate?)
        active_session = win32ts.WTSGetActiveConsoleSessionId()
        if active_session is not None and active_session != UserAccounts.WTS_INVALID_SESSION_ID:
            wts_sessions.append(active_session)
        
        # Convert sessions to users and check their group membership
        for session in wts_sessions:
            user_name = win32ts.WTSQuerySessionInformation(None, session, win32ts.WTSUserName)
            if user_name is not None and user_name != "":
                if UserAccounts.is_user_in_group(user_name, "OPEStudents"):
                    ret.append(user_name)
                
        return ret

    @staticmethod
    def is_uac_admin():
        ret = False
        r = ctypes.windll.shell32.IsUserAnAdmin()
        if r == 1:
            ret = True
        
        return ret

    @staticmethod
    def is_in_admin_group(user_name=None):
        # Get the list of groups for this user - if not in admin, return false
        ret = False
        
        try:
            server_name = None  # None for local machine
            if user_name is None:
                user_name = win32api.GetUserName()
            if user_name == "SYSTEM":
                # SYSTEM user counts!
                return True

            # p("}}ynChecking Admin Membership for: " + user_name)
            groups = win32net.NetUserGetLocalGroups(server_name, user_name, 0)

            for g in groups:
                if g.lower() == "administrators":
                    ret = True
        except Exception as ex:
            p("}}rnERROR - Unknown Error! }}xx\n" + str(ex))
            ret = False

        return ret

    @staticmethod
    def is_user_in_group(user_name, group_name):
        ret = False

        try:
            server_name = None  # for local machine
            groups = win32net.NetUserGetLocalGroups(server_name, user_name, 0)

            for g in groups:
                if g.lower() == group_name.lower():
                    # Found group!
                    ret = True
                    break   # Break out of loop

        except Exception as ex:
            p("}}rnERROR - Unknown Error trying to get groups for user!]n}}xx" + \
                str(ex))
            return None
        return ret

    @staticmethod
    def elevate_process_privilege_to_backup_restore():
        #add_privilege=ntsecuritycon.SE_RESTORE_NAME | 
        #ntsecuritycon.SE_BACKUP_NAME ):
        try:
            se_backup_value = win32security.LookupPrivilegeValue(None, ntsecuritycon.SE_BACKUP_NAME)
            se_restore_value = win32security.LookupPrivilegeValue(None, ntsecuritycon.SE_RESTORE_NAME)

            flags = ntsecuritycon.TOKEN_ADJUST_PRIVILEGES \
                | ntsecuritycon.TOKEN_QUERY
            
            proces_token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), flags)

            # Add backup/restore privileges
            new_privs = [(se_backup_value, ntsecuritycon.SE_PRIVILEGE_ENABLED),
                    (se_restore_value, ntsecuritycon.SE_PRIVILEGE_ENABLED)]

            win32security.AdjustTokenPrivileges(proces_token, 0, new_privs)
        except Exception as ex:
            p("}}rbException - trying to elveate backup/restore privileges}}xx\n" +
                str(ex))
            return False

        return True

    @staticmethod
    def elevate_process_privilege_to_tcb():
        try:
            se_tcb_value = win32security.LookupPrivilegeValue(None, ntsecuritycon.SE_TCB_NAME)

            flags = ntsecuritycon.TOKEN_ADJUST_PRIVILEGES \
                | ntsecuritycon.TOKEN_QUERY
            
            proces_token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), flags)

            # Add backup/restore privileges
            new_privs = [
                (se_tcb_value, ntsecuritycon.SE_PRIVILEGE_ENABLED),
            ]

            win32security.AdjustTokenPrivileges(proces_token, 0, new_privs)
        except Exception as ex:
            p("}}rbException - trying to elveate tcb privileges}}xx\n" +
                str(ex))
            return False

        return True
    
    @staticmethod
    def generate_random_password():
        ret = ""

        # Get one upper case
        ret += chr(random.randint(65,90))
        # Get one lower case
        ret += chr(random.randint(97, 122)) 
        # get one number
        ret += chr(random.randint(48,57))

        # get one symbol
        ret += chr(random.randint(58,64))
        # 7 randoms
        for i in range(1,7):
            ret += chr(random.randint(35,125))

        # Don't use \ or ' or " charcters
        ret = ret.replace("'", "").replace("\"", "").replace("\\", "")
        return ret

    @staticmethod
    def create_local_student_account(user_name=None, full_name=None, password=None):
        ret = True
        # Make sure we have parameters
        if user_name is None:
            user_name = util.get_param(2, None)
        if full_name is None:
            full_name = util.get_param(3, None)
        if password is None:
            password = util.get_param(4, None)
        if user_name is None or full_name is None or password is None:
            p("}}rbError - Invalid parameters to create new student user!}}xx", debug_level=1)
            return False

        # Create local student account
        try:
            p("}}yn\tAdding student account (" + user_name + ")...}}xx")
            accounts.User.create(user_name, password)
        # except pywintypes.error as ex:
        except Exception as ex:
            if ex.args[2] == "The account already exists.":
                pass
            else:
                # Unexpected error
                p("}}rb" + str(ex) + "}}xx")
                ret = False

        # Set info for the student
        user_data = dict()
        user_data['name'] = user_name
        user_data['full_name'] = full_name
        # Start w a random complex password
        user_data['password'] = UserAccounts.generate_random_password()  # password
        # NOTE - Student accounts are always created disabled!
        user_data['flags'] = UserAccounts.DISABLE_ACCOUNT_FLAGS
        user_data['priv'] = win32netcon.USER_PRIV_USER
        user_data['comment'] = 'OPE Student Account'
        # user_data['home_dir'] = home_dir
        # user_data['home_dir_drive'] = "h:"
        user_data['primary_group_id'] = ntsecuritycon.DOMAIN_GROUP_RID_USERS
        user_data['password_expired'] = 0
        user_data['acct_expires'] = win32netcon.TIMEQ_FOREVER
        
        win32net.NetUserSetInfo(None, user_name, 3, user_data)

        # Make sure the password is complex enough
        tmp_password = password
        if len(tmp_password) < 8:
            p("}}rbStudent Password Too Short! Padding with !s to 8 characters}}xx")
            pad_chars = (8-len(tmp_password)) * "!"
        # Set the password
        try:
            user_data['password'] = tmp_password
            win32net.NetUserSetInfo(None, user_name, 3, user_data)
        except Exception as ex:
            p("}}rbERROR setting password for " + user_name + "}}xx\n" + str(ex))

        # Add student to the students group
        p("}}yn\tAdding student to students group...}}xx")

        if not UserAccounts.set_default_groups_for_student(user_name):
            ret = False

        return ret

    @staticmethod
    def create_local_admin_account(user_name, full_name, password):
        # Create local admin account
        ret = True
                
        try:
            p("}}yn\tAdding Admin account (" + user_name + ")...}}xx")
            accounts.User.create(user_name, password)
            # p("}}yn\t\tDone.}}xx")
        # except pywintypes.error as ex:
        except Exception as ex:
            if ex.args[2] == "The account already exists.":
                pass
            else:
                # Unexpected error
                p("}}rb" + str(ex) + "}}xx")
                ret = False

        user_data = dict()
        user_data['name'] = user_name
        user_data['full_name'] = full_name
        #user_data['password'] = UserAccounts.generate_random_password()
        user_data['flags'] = UserAccounts.ENABLE_ACCOUNT_FLAGS
        user_data['priv'] = win32netcon.USER_PRIV_ADMIN
        user_data['comment'] = 'OPE Admin Account'
        # user_data['home_dir'] = home_dir
        # user_data['home_dir_drive'] = "h:"
        user_data['primary_group_id'] = ntsecuritycon.DOMAIN_GROUP_RID_USERS
        user_data['password_expired'] = 0
        user_data['acct_expires'] = win32netcon.TIMEQ_FOREVER
        
        win32net.NetUserSetInfo(None, user_name, 3, user_data)

        # Set password
        try:
            user_data['password'] = password
            win32net.NetUserSetInfo(None, user_name, 3, user_data)
        except Exception as ex:
            p("}}rbERROR setting password for " + user_name + "}}xx\n" + str(ex))
        
        if not UserAccounts.set_default_groups_for_admin(user_name):
            ret = False

        return ret

    @staticmethod
    def create_local_students_group():
        # Make sure the group in question exists
        ret = False

        try:
            accounts.LocalGroup.create(UserAccounts.STUDENTS_GROUP)
            ret = True
        except Exception as ex:
            if ex.args[2] == "The specified local group already exists.":
                ret = True
                pass
            else:
                # Unexpected error
                p("}}rb" + str(ex) + "}}xx")
                ret = False

        return ret

    @staticmethod
    def disable_account(account_name=None):
        if account_name is None:
            account_name = util.get_param(2, None)
        if account_name is None:
            p("}}enInvalid User name - not disabling account!}}xx")
            return False
        try:
            user_data = dict()
            user_data['flags'] = UserAccounts.DISABLE_ACCOUNT_FLAGS
            #win32netcon.UF_SCRIPT | win32netcon.UF_ACCOUNTDISABLE
            win32net.NetUserSetInfo(None, account_name, 1008, user_data)
        except Exception as ex:
            p("}}rnError - Unable to disable account: " + str(account_name) + "}}xx\n" + \
                str(ex))
            return False
        return True
    
    @staticmethod
    def add_user_to_group(user_name, group_name):
        try:
            # Get the group
            grp = accounts.LocalGroup(accounts.group(group_name).sid)
            # Get the user
            user = accounts.user(user_name)

            grp.add(user)
        except Exception as ex:
            if ex.args[2] == "The specified account name is already a member of the group.":
                pass
            else:
                p("}}rbERROR - Unexpected exception trying to add user to group (" + \
                    user_name + "/" + group_name + "\n}}xx" + str(ex))
                return False
        return True

    @staticmethod
    def set_default_groups_for_admin(account_name = None):
        ret = True
        # Make sure the student is in the proper groups
        if account_name is None:
            account_name = util.get_param(2, None)
        if account_name is None:
            p("}}rnInvalid User name - not adding default admin groups to account!}}xx")
            return False

        # Make sure students group exists
        ret = UserAccounts.create_local_students_group()

        if not UserAccounts.add_user_to_group(account_name, "Administrators"):
            ret = False
        
        if not UserAccounts.add_user_to_group(account_name, "Users"):
            ret = False
        
        # # home_dir = "%s\\%s" % (server_name, user_name)
        #

        return ret

    @staticmethod
    def set_default_groups_for_student(account_name = None):
        ret = True
        # Make sure the student is in the proper groups
        if account_name is None:
            account_name = util.get_param(2, None)
        if account_name is None:
            p("}}rnInvalid User name - not adding default groups to user account!}}xx")
            return False

        # Make sure students group exists
        ret = UserAccounts.create_local_students_group()

        if not UserAccounts.add_user_to_group(account_name, UserAccounts.STUDENTS_GROUP):
            ret = False
        
        if not UserAccounts.add_user_to_group(account_name, "Users"):
            ret = False
        
        # # home_dir = "%s\\%s" % (server_name, user_name)
        #

        return ret

    @staticmethod
    def enable_account(account_name=None):
        if account_name is None:
            account_name = util.get_param(2, None)
        if account_name is None:
            p("}}rnInvalid User name - not enabling account!}}xx")
            return False
        
        try:
            user_data = dict()
            user_data['flags'] = UserAccounts.ENABLE_ACCOUNT_FLAGS
            #win32netcon.UF_SCRIPT | win32netcon.UF_ACCOUNTDISABLE
            win32net.NetUserSetInfo(None, account_name, 1008, user_data)
        except Exception as ex:
            p("}}rnError - Unable to enable account: " + str(account_name) + "}}xx\n" + \
                str(ex))
            return False
        
        return True

    @staticmethod
    def disable_student_accounts():
        ret = True
        # Get a list of accounts that are in the students group
        
        p("}}cb-- Disabling local student accounts in " + str(UserAccounts.STUDENTS_GROUP) + " group...}}xx")
        try:
            grp = accounts.local_group(UserAccounts.STUDENTS_GROUP)
        except winsys.exc.x_not_found as ex:
            # p("}}yn" + str(UserAccounts.STUDENTS_GROUP) + " group not found - skipping disable student accounts...}}xx")
            return True
        
        for user in grp:
            user_name = str(user.name)
            p("}}cn-" + user_name + "}}xx")
            if not UserAccounts.disable_account(user_name):
                ret = False
        
        return ret
    
    @staticmethod
    def remove_account_profile(user_name=None):
        # Remove the profile/files for the user
        if user_name is None:
            user_name = util.get_param(2, None)
        if user_name is None:
            p("}}enInvalid User name - not removing account profile!}}xx")
            return False
        
        # Log it out (if it is logged in)
        UserAccounts.log_out_user(user_name)
        
        # Get the SID for the user in question
        user_sid = ""
        try:
            parts = win32security.LookupAccountName(None, user_name)
            user_sid = win32security.ConvertSidToStringSid(parts[0])
        except Exception as ex:
            # Unable to find this user?
            p("}}rnError - Invalid User - can't remove profile!}}xx " + str(user_name))
            return False
        
        if user_sid == "":
            # User doesn't exist?
            p("}}rnInvalid User - can't remove profile!}}xx " + str(user_name))
            return False
        
        # We need more privileges to do this next part
        UserAccounts.elevate_process_privilege_to_backup_restore()
        
        # Make sure the registry hive is unloaded
        #p("Unloading " + user_sid)
        try:
            win32api.RegUnLoadKey(win32con.HKEY_USERS, user_sid)
        except Exception as ex:
            p("}}ynUnable to unload user registry - likely not currently loaded, moving on...}}xx", debug_level=4)

        try:
            win32profile.DeleteProfile(user_sid)
        except Exception as ex:
            p("}}ynUnable to remove profile folder - likely it doesn't exist.}}xx", debug_level=4)
        return True
        
        #See if a profile exists
        w = wmi.WMI()
        profiles = w.Win32_UserProfile(SID=user_sid)
        if len(profiles) < 1:
            p("}}ynNo profile found for this user, skipping remove!}}xx")
            return True
        
        profile_path = ""
        profile_loaded = False
        for profile in profiles:
            profile_path = profile.LocalPath
            profile_loaded = profile.Loaded
        profiles = None
                
        # We know it exists
        

        # Remove it from the registry list
        RegistrySettings.remove_key("HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\" + \
            "ProfileList\\" + user_sid)

        # Delete the folder/files
        try:
            shutil.rmtree(profile_path)
        except Exception as ex:
            p("}}rnError - Unable to remove the profile folder at " + profile_path + "}}xx\n" + \
                str(ex))
            return False

        return True

    @staticmethod
    def lock_screen_for_user(user_name=None):
        # Find the user in question and lock the workstation
        if user_name is None:
            user_name = util.get_param(2, None)
        if user_name is None:
            # Lock for the current user if no name
            return UserAccounts.lock_screen_for_current_user()
        

        p("}}ybLocking screen for other users - Not Implemented Yet!}}xx")
        # TODO - lock_workstation
        # Lookup the user specified and run this under their account

        return False
        
    
    @staticmethod
    def lock_screen_for_current_user():
        # Locks the workstation of the current user
        return ctypes.windll.user32.LockWorkStation()

    @staticmethod
    def log_out_all_students():
        # Get a list of users who are in the students group and log them out.

        students = UserAccounts.get_student_login_sessions()
        p("}}cb-- Logging out all student accounts ...}}xx")
        for student in students:
            p("}}cn-" + student + "}}xx", log_level=1)
            UserAccounts.log_out_user(student)

        return True

    @staticmethod
    def log_out_user(user_name=None):
        if user_name is None:
            user_name = util.get_param(2, None)
        if user_name is None:
            p("}}rn No User name provided - not logging out!}}xx")
            return False
        
        # Get list of current sessions
        sessions = win32ts.WTSEnumerateSessions(None, 1, 0)

        logged_off = False
        
        for session in sessions:
            active_session = session['SessionId']
            station_name = session["WinStationName"]

            # Get the user for this session
            logged_in_user_name = win32ts.WTSQuerySessionInformation(None, active_session,
                win32ts.WTSUserName)
            
            #p("}}ynComparing: " + str(user_name) + "/" + logged_in_user_name)
            if user_name == logged_in_user_name:
                # Log this one out
                p("}}gnLogging off " + str(user_name) + " - typically takes 10-120 seconds...}}xx", debug_level=4)
                win32ts.WTSLogoffSession(None, active_session, True)
                logged_off = True

        if logged_off is not True:
            p("}}ybUser not logged in - skipping log off! " + str(user_name) + "}}xx", debug_level=5)
        else:
            p("}}gnUser logged out! " + str(user_name) + "}}xx", debug_level=3)

        return True

    @staticmethod
    def delete_user(user_name=None):
        if user_name is None:
            user_name = util.get_param(2, None)
        if user_name is None:
            p("}}enInvalid User name - not removing account!}}xx")
            return False
        curr_user = None
        try:
            curr_user = accounts.principal(user_name)
        except Exception as ex:
            p("}}rbInvalid User Account - Not deleting!}}xx", debug_level=1)
            return False

        # Remove the profile first
        ret = UserAccounts.remove_account_profile(user_name)

        # Remove the local user
        try:
            curr_user.delete()
        except Exception as ex:
            p("}}rbError - Unable to remove account: " + str(user_name) + "}}xx\n" + str(ex))
            return False
        
        return True
    
    @staticmethod
    def disable_guest_account():
        try:
            UserAccounts.disable_account("Guest")
        except Exception as ex:
            p("}}rbERROR disabling guest account " + str(ex) + "}}xx")
            return False
        
        # Run this to disable the guest account?
        # NET USER Guest /ACTIVE:no
        return True
  

if __name__ == "__main__":
    #ret = UserAccounts.create_local_students_group()
    #ret = UserAccounts.create_local_student_account("s999999", "Test Student", "Sid999999!")
    #print("RET: " + str(ret))
    print("Log out all students...")
    #print(UserAccounts.get_active_user_name())
    UserAccounts.log_out_all_students()