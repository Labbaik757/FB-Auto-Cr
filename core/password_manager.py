import random
import string
from ui.colors import GREEN, RED, WHITE, YELLOW, CYAN, EKL, LINE
from core.settings_manager import load_settings


# Generate a strong random password matching security criteria
def generate_random_password():
    return ''.join(random.choices(
        string.ascii_letters + string.digits + '!@#$%^&*',
        k=random.randint(8, 14)
    ))


# Prompt user for password preference or use settings configuration
def select_password_config(config_state=None, render_callback=None):
    settings = load_settings()
    pwd_cfg = settings.get("password_settings", {})
    ask_pwd = pwd_cfg.get("ask_for_password", True)
    def_pwd = str(pwd_cfg.get("default_password", "")).strip()
    use_random = pwd_cfg.get("use_random_password", True)

    # Check if configured to skip interactive prompt
    if not ask_pwd:
        if def_pwd:
            if config_state is not None:
                config_state["password"] = f"Fixed ({def_pwd}) [Settings]"
            if render_callback:
                render_callback()
            return {"type": "fixed", "value": def_pwd}
        elif use_random:
            if config_state is not None:
                config_state["password"] = "Random Password [Settings]"
            if render_callback:
                render_callback()
            return {"type": "random", "value": None}

    if render_callback:
        render_callback()

    print(f" {GREEN}[{RED}01{GREEN}] Random Password {WHITE}(Auto-generated strong password)")
    print(f" {GREEN}[{RED}02{GREEN}] Custom / Fixed Password {WHITE}(Use a specific password for all accounts)")
    if def_pwd:
        print(f" {GREEN}[{RED}03{GREEN}] Use Saved Password {WHITE}({def_pwd})")
    print(f"{LINE}")

    while True:
        try:
            choice = input(f" {GREEN}[{RED}●{GREEN}] Select Password Type (1/2) {EKL} ").strip()
            if choice == "1" or not choice:
                if config_state is not None:
                    config_state["password"] = "Random Password"
                if render_callback:
                    render_callback()
                return {"type": "random", "value": None}
            elif choice == "2":
                while True:
                    custom_pwd = input(f" {GREEN}[{RED}●{GREEN}] Enter Custom Password {EKL} ").strip()
                    if len(custom_pwd) >= 6:
                        if config_state is not None:
                            config_state["password"] = f"Custom ({custom_pwd})"
                        if render_callback:
                            render_callback()
                        return {"type": "fixed", "value": custom_pwd}
                    print(f"{RED} Password must be at least 6 characters!")
            elif choice == "3" and def_pwd:
                if config_state is not None:
                    config_state["password"] = f"Saved ({def_pwd})"
                if render_callback:
                    render_callback()
                return {"type": "fixed", "value": def_pwd}
            else:
                print(f"{RED} Invalid choice! Enter 1 or 2.")
        except KeyboardInterrupt:
            raise
        except Exception:
            pass
