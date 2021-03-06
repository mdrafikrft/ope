
import os
import sys
import traceback
import logging

# try:
#     import _winreg as winreg
# except:
#     import winreg

import win32api    
#import winsys
from winsys import accounts, registry, security
from winsys.registry import REGISTRY_ACCESS

# Monkeypatch to force stuff in the registry class to do 64 bit registry access always even if we are a 32 bit process
registry.Registry.DEFAULT_ACCESS=REGISTRY_ACCESS.KEY_READ|REGISTRY_ACCESS.KEY_WOW64_64KEY

# Hide winsys logs
winsys_logger = logging.getLogger("winsys")
winsys_logger.setLevel(50)  # CRITIAL = 50

from color import p
import util

class RegistrySettings:
    # Default registry path where settings are stored    
    ROOT_PATH = "HKLM\\Software\\OPE"

    @staticmethod
    def is_debug():
        val = RegistrySettings.get_reg_value(value_name="debug", default="off")
        if val == "on":
            return True
        
        return False

    @staticmethod
    def test_reg():
        canvas_access_token = "2043582439852400"
        canvas_url = "https://canvas.ed"
        smc_url = "https://smc.ed"
        student_user = "777777"
        student_name = "Bob Smith"
        admin_user = "huskers"
        
        RegistrySettings.store_credential_info(canvas_access_token, canvas_url, smc_url,
            student_user, student_name, admin_user)
        p("Student: " + RegistrySettings.get_reg_value(value_name="student_user", default=""))
        p("Admin: " + RegistrySettings.get_reg_value(app="OPEService", value_name="admin_user", default="administrator"))

        #RegistrySettings.set_reg_value(app="TESTOPE", value_name="TestValue", value="slkfjsdl")

        log_level = RegistrySettings.get_reg_value(app="OPEService", value_name="log_level", default=10,
            value_type="REG_DWORD")
        p("Log Level: ", log_level)


        # key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, "Software\OPE", 0,
        #     winreg.KEY_WOW64_64KEY | winreg.KEY_READ)
        
        # p("SUB KEYS: ")
        # enum_done = False
        # i = 0
        # try:
        #     while enum_done is False:
        #         sub_key = winreg.EnumKey(key, i)
        #         p("-- SK: " + str(sub_key))
        #         i += 1
        #         # p("Ref: " + str(winreg.QueryReflectionKey(winreg.HKEY_LOCAL_MACHINE)))
        # except WindowsError as ex:
        #     # No more values
        #     if ex.errno == 22:
        #         # p("---_DONE")
        #         # Don't flag an error when we are out of entries
        #         pass
        #     else:
        #         p("-- ERR " + str(ex) + " " + str(ex.errno))
        #     pass
            
        #reg = registry.registry(r"HKLM\Software\OPETEST",
        #        access=REGISTRY_ACCESS.KEY_ALL_ACCESS|REGISTRY_ACCESS.KEY_WOW64_64KEY)
        #reg.create()

    @staticmethod
    def add_mgmt_utility_to_path():
        # Add the mgmt utility path environment variable

        # System env path
        # HLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment
        # User path
        # HKEY_CURRENT_USER\Environment\Path
        # Application Path
        # HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\

        # Grab the system path variable

        sys_path = RegistrySettings.get_reg_value(root="HKLM\\SYSTEM\\CurrentControlSet",
            app="Control", subkey="Session Manager\\Environment",
            value_name="Path", default="")
        
        if sys_path == "":
            p("}}rbUnable to grab System path variable!}}xx")
            return False
        
        mgmt_path = "%programdata%\\ope\\Services\\mgmt\\"
        if not mgmt_path in sys_path:
            sys_path += ";" + mgmt_path
        
        #p("}}ynNew Path: " + sys_path + "}}xx")

        RegistrySettings.set_reg_value(root="HKLM\\SYSTEM\\CurrentControlSet",
            app="Control", subkey="Session Manager\\Environment",
            value_name="Path", value=sys_path)
        
        p("}}gnAdded to system path.")
        p("}}gbYou will need to open a new command prompt for the change to take effect.}}xx")
    
        return True

    @staticmethod
    def remove_key(key_path):
        try:
            # Open the key
            key = registry.registry(key_path, 
                access=REGISTRY_ACCESS.KEY_READ|REGISTRY_ACCESS.KEY_WOW64_64KEY)
            key.delete()
        except Exception as ex:
            p("}}rnError - couldn't remove registry key }}xx\n" + str(key_path) + "\n" + \
                str(ex), debug_level=1)
            return False
        
        return True

    @staticmethod
    def get_reg_value(root="", app="", subkey="", value_name="", default="",
        value_type=""):
        ret = default

        if root == "":
            root = RegistrySettings.ROOT_PATH

        # Combine parts
        path = os.path.join(root, app, subkey).replace("\\\\", "\\")
        # Make sure we don't have a tailing \\
        path = path.strip("\\")
        # p("path: " + path)

        try:
            # Open the key
            key = registry.registry(path, 
                access=REGISTRY_ACCESS.KEY_READ|REGISTRY_ACCESS.KEY_WOW64_64KEY)
            # Make sure the key exists
            key.create()
            
            val = key.get_value(value_name)
            # p("Got Val: " + str(val))

            if value_type == "REG_SZ":
                ret = str(val)
            elif value_type == "REG_DWORD":
                ret = int(val)
            else:
                ret = val
        except Exception as ex:
            #p("}}rbException! - Error pulling value from registry! Returning default value}}xx\n    (" +
            #    path + ":" + value_name + "=" + str(default_value)+")")
            #p(str(ex))
            pass

        return ret
    
    @staticmethod
    def set_reg_value(root="", app="", subkey="", value_name="", value="", value_type=""):
        ret = False

        if root == "":
            root = RegistrySettings.ROOT_PATH

        # Combine parts
        path = os.path.join(root, app, subkey).replace("\\\\", "\\")
        # Make sure we don't have a tailing \\
        path = path.strip("\\")
        # p("path: " + path)

        reg_type = None

        try:
            # Convert the value to the correct type
            if value_type == "REG_SZ":
                #p("}}ynSetting To String}}xx")
                value = str(value)
                reg_type = registry.REGISTRY_VALUE_TYPE.REG_SZ
            elif value_type == "REG_DWORD":
                value = int(value)
                reg_type = registry.REGISTRY_VALUE_TYPE.REG_DWORD
            
            # Open the key
            key = registry.registry(path, 
                access=REGISTRY_ACCESS.KEY_ALL_ACCESS|REGISTRY_ACCESS.KEY_WOW64_64KEY)
            # Make sure the key exists
            key.create()
            key.set_value(value_name, value, reg_type)
            #key[value_name] = value
                        
            ret = True
        except Exception as ex:
            p("}}rbException! - Error setting registry value!}}xx\n\t(" +
                path + ":" + value_name + "=" + str(value)+")")
            p("\t" + str(ex))
            pass

        return ret

    @staticmethod
    def store_credential_info(canvas_access_token, canvas_url, smc_url,
            student_user, student_name, admin_user):
        # Store credential info in the proper places
        RegistrySettings.set_reg_value(app="", value_name="canvas_access_token",
            value=canvas_access_token, value_type="REG_SZ")
        RegistrySettings.set_reg_value(app="OPELMS\student", value_name="canvas_access_token",
            value=canvas_access_token, value_type="REG_SZ")

        RegistrySettings.set_reg_value(app="", value_name="canvas_url", value=canvas_url,
            value_type="REG_SZ")
        RegistrySettings.set_reg_value(app="OPELMS\student", value_name="canvas_url",
            value=canvas_url, value_type="REG_SZ")

        RegistrySettings.set_reg_value(app="", value_name="smc_url", value=smc_url,
            value_type="REG_SZ")
        RegistrySettings.set_reg_value(app="OPELMS\student", value_name="smc_url",
            value=smc_url, value_type="REG_SZ")

        RegistrySettings.set_reg_value(app="", value_name="student_user", value=student_user,
            value_type="REG_SZ")
        RegistrySettings.set_reg_value(app="OPELMS\student", value_name="user_name",
            value=student_user, value_type="REG_SZ")

        RegistrySettings.set_reg_value(app="", value_name="student_name", value=student_name,
            value_type="REG_SZ")

        RegistrySettings.set_reg_value(app="OPEService", value_name="admin_user", value=admin_user,
            value_type="REG_SZ")

        return True

    @staticmethod
    def set_default_ope_registry_permissions(student_user = "", laptop_admin_user = ""):
        try:
            if student_user == "":
                student_user = RegistrySettings.get_reg_value(value_name="student_user", default="")

            if laptop_admin_user == "":
                laptop_admin_user = RegistrySettings.get_reg_value(app="OPEService", value_name="admin_user", default="administrator")
            
            if laptop_admin_user == "":
                laptop_admin_user = None
            
            if student_user == "":
                p("}}rnNo credentialed student set!}}xx")
                #return False
                student_user = None
            
            # Make sure this user exists
            if student_user is not None:
                try:
                    # Will throw an exception if the user doesn't exist
                    student_p = accounts.principal(student_user)
                except Exception as ex:
                    # Invalid student account
                    p("}}rbInvalid Student Account - skipping permissions for this account: " + str(student_user) + "}}xx")
                    student_user = None
            
            # Make sure the admin user exists
            if laptop_admin_user is not None:
                try:
                    admin_p = accounts.principal(laptop_admin_user)
                except Exception as ex:
                    # Invalid admin account!
                    p("}}rbInvalid Admin Account - skipping permissions for this account: " + str(laptop_admin_user) + "}}xx")
                    laptop_admin_user = None

            base_dacl = [
                ("Administrators", registry.Registry.ACCESS["F"], "ALLOW"),
                ("SYSTEM", registry.Registry.ACCESS["F"], "ALLOW"),
                #("Users", registry.Registry.ACCESS["Q"], "ALLOW")
            ]
            service_base_dacl = [
                ("Administrators", registry.Registry.ACCESS["F"], "ALLOW"),
                ("SYSTEM", registry.Registry.ACCESS["F"], "ALLOW"),
                # Don't let regular users read OPEService key
                #("Users", registry.Registry.ACCESS["Q"], "ALLOW")
            ]

            logged_in_user = win32api.GetUserName()
            if logged_in_user.upper() != "SYSTEM" and logged_in_user != "":
                base_dacl.append((logged_in_user, registry.Registry.ACCESS["F"], "ALLOW"))
                service_base_dacl.append((logged_in_user, registry.Registry.ACCESS["F"], "ALLOW"))

            if laptop_admin_user is not None and laptop_admin_user != "":
                # Make sure this admin has registry access
                base_dacl.append((laptop_admin_user, registry.Registry.ACCESS["F"], "ALLOW"))
                service_base_dacl.append((laptop_admin_user, registry.Registry.ACCESS["F"], "ALLOW"))

            # Make sure the logging registry key has proper permissions
            reg = registry.registry(r"HKLM\System\CurrentControlSet\Services\EventLog\Application\OPE",
                access=REGISTRY_ACCESS.KEY_ALL_ACCESS|REGISTRY_ACCESS.KEY_WOW64_64KEY)
            reg.create()
            with reg.security() as s:
                # Break inheritance causes things to reapply properly
                s.break_inheritance(copy_first=True)
                #s.dacl = base_dacl
                s.dacl.append(("Everyone",
                    registry.Registry.ACCESS["R"],
                    "ALLOW"))
                # s.dacl.dump()

            reg = registry.registry(r"HKLM\Software\OPE",
                access=REGISTRY_ACCESS.KEY_ALL_ACCESS|REGISTRY_ACCESS.KEY_WOW64_64KEY)
            reg.create()
            with reg.security() as s:
                # Break inheritance causes things to reapply properly
                s.break_inheritance(copy_first=True)
                s.dacl = base_dacl
                if student_user is not None:
                    s.dacl.append((student_user, registry.Registry.ACCESS["R"], "ALLOW"))
                s.dacl.append(("Everyone",
                    registry.Registry.ACCESS["R"],
                    "ALLOW"
                ))
                # s.dacl.dump()
            
            reg = registry.registry(r"HKLM\Software\OPE\OPELMS",
                access=REGISTRY_ACCESS.KEY_ALL_ACCESS|REGISTRY_ACCESS.KEY_WOW64_64KEY)
            reg.create()
            with reg.security() as s:
                # Break inheritance causes things to reapply properly
                s.break_inheritance(copy_first=True)
                s.dacl = base_dacl
                if student_user is not None:
                    s.dacl.append((student_user, registry.Registry.ACCESS["C"],
                    "ALLOW"))
                s.dacl.append(("Everyone",
                    registry.Registry.ACCESS["R"],
                    "ALLOW"
                ))
                # s.dacl.dump()
            
            reg = registry.registry(r"HKLM\Software\OPE\OPEService",
                access=REGISTRY_ACCESS.KEY_READ|REGISTRY_ACCESS.KEY_WOW64_64KEY)
            reg.create()
            with reg.security() as s:
                # Break inheritance causes things to reapply properly
                s.break_inheritance(copy_first=True)
                s.dacl = service_base_dacl
                #if student_user is not None:
                #    s.dacl.append((student_user, registry.Registry.ACCESS["Q"], "ALLOW"))
                # s.dacl.dump()
            
            reg = registry.registry(r"HKLM\Software\OPE\OPELMS\student",
                access=REGISTRY_ACCESS.KEY_READ|REGISTRY_ACCESS.KEY_WOW64_64KEY)
            reg.create()
            with reg.security() as s:
                # Break inheritance causes things to reapply properly
                s.break_inheritance(copy_first=True)
                s.dacl = base_dacl
                if student_user is not None:
                    s.dacl.append((student_user, registry.Registry.ACCESS["C"],
                    "ALLOW"))
                s.dacl.append(("Everyone",
                    registry.Registry.ACCESS["R"],
                    "ALLOW"
                ))
                # s.dacl.dump()

            p("}}gnRegistry Permissions Set}}xx", log_level=3)
        except Exception as ex:
            p("}}rbUnknown Exception! }}xx\n" + str(ex))
            return False
        return True

    @staticmethod
    def set_screen_shot_timer():
        # Set how often to reload scan nics
        param = util.get_param(2)
        if param == "":
            p("}}rnInvalid frequency Specified}}xx")
            return False
        
        frequency = "30-300"
        try:
            frequency = str(param)
        except:
            # Not an int? Set it as a string
            frequency = param
            #p("}}rnInvalid frequency Specified}}xx")
            #return False

        # Set the registry setting
        RegistrySettings.set_reg_value(app="OPEService", value_name="screen_shot_timer",
            value=frequency)
        return True

    @staticmethod
    def set_log_level():
        # Set the log level parameter in the registry
        param = util.get_param(2)
        if param == "":
            p("}}rnInvalid Log Level Specified}}xx")
            return False
        
        log_level = 3
        try:
            log_level = int(param)
        except:
            p("}}rnInvalid Log Level Specified}}xx")
            return False

        # Set the registry setting
        RegistrySettings.set_reg_value(app="OPEService", value_name="log_level", value=log_level)
        return True

    @staticmethod
    def set_default_permissions_timer():
        # Set how often to reset permissions in the registry
        param = util.get_param(2)
        if param == "":
            p("}}rnInvalid frequency Specified}}xx")
            return False
        
        frequency = 3600
        try:
            frequency = int(param)
        except:
            p("}}rnInvalid frequency Specified}}xx")
            return False

        # Set the registry setting
        RegistrySettings.set_reg_value(app="OPEService", value_name="set_default_permissions_timer", value=frequency)
        return True

    @staticmethod
    def set_reload_settings_timer():
        # Set how often to reload settings from the registry
        param = util.get_param(2)
        if param == "":
            p("}}rnInvalid frequency Specified}}xx")
            return False
        
        frequency = 30
        try:
            frequency = int(param)
        except:
            p("}}rnInvalid frequency Specified}}xx")
            return False

        # Set the registry setting
        RegistrySettings.set_reg_value(app="OPEService", value_name="reload_settings_timer", value=frequency)
        return True

    @staticmethod
    def set_scan_nics_timer():
        # Set how often to reload scan nics
        param = util.get_param(2)
        if param == "":
            p("}}rnInvalid frequency Specified}}xx")
            return False
        
        frequency = 60
        try:
            frequency = int(param)
        except:
            p("}}rnInvalid frequency Specified}}xx")
            return False

        # Set the registry setting
        RegistrySettings.set_reg_value(app="OPEService", value_name="scan_nics_timer", value=frequency)
        return True


if __name__ == "__main__":
    p("Running Tests...")
    RegistrySettings.test_reg()