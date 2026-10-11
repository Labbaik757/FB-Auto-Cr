import os
import platform
from ui.colors import GREEN, CYAN, RED, ORANGE, LINE

VERSION = "1.0.0"


# Clear terminal screen (cross-platform)
def clear():
    if platform.system() == "Windows":
        os.system("cls")
    else:
        os.system("clear")


# Display the tool banner with ASCII art logo and info
def logo():
    clear()
    print(f"""{GREEN}
      d8888b. db    db db   dD
      88  `8D 88    88 88 ,8P'
      88   88 88    88 88,8P
      88   88 88    88 88`8b
      88  .8D 88b  d88 88 `88.
      Y8888D' ~Y8888P' YP   YD   {ORANGE}V-{VERSION}
{LINE}
 {GREEN}[{RED}●{GREEN}] TOOL OWNER   {CYAN}:{GREEN} @Labbaik757
 {GREEN}[{RED}●{GREEN}] TOOL         {CYAN}:{GREEN} AUTO CREATE
 {GREEN}[{RED}●{GREEN}] TOOL STATUS  {CYAN}:{GREEN} PAID
{LINE}""")
