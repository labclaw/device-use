"""Shared terminal styling for device-use demos.

Extracted from the common pattern duplicated across 10+ demo scripts.
Import these instead of copy-pasting ANSI codes.
"""

# ── ANSI Color Constants ────────────────────────────────────────

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"
WHITE = "\033[37m"
RESET = "\033[0m"

# ── Compound Symbols ────────────────────────────────────────────

CHECK = f"{GREEN}✓{RESET}"
ARROW = f"{CYAN}→{RESET}"
WARN = f"{YELLOW}○{RESET}"
STAR = f"{YELLOW}★{RESET}"
FAIL = f"{RED}✗{RESET}"


# ── Output Helpers ──────────────────────────────────────────────

def banner(title: str, subtitle: str = "", product: str = "device-use") -> None:
    """Print a styled banner header."""
    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   {RESET}{BOLD}{title}{RESET}{BOLD}{CYAN}{' ' * max(0, 59 - len(title))}║
║   {RESET}{DIM}{subtitle}{RESET}{BOLD}{CYAN}{' ' * max(0, 59 - len(subtitle))}║
║                                                              ║
║   {RESET}{DIM}{product} | ROS for Lab Instruments{RESET}{BOLD}{CYAN}{' ' * max(0, 35 - len(product))}║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝{RESET}
""")


def step(n: int, text: str) -> None:
    """Print a numbered step separator."""
    print(f"\n{BOLD}{MAGENTA}{'━' * 62}{RESET}")
    print(f"  {BOLD}Step {n}{RESET} {DIM}│{RESET} {text}")
    print(f"{BOLD}{MAGENTA}{'━' * 62}{RESET}\n")


def phase(n: int, title: str, subtitle: str = "") -> None:
    """Print a numbered phase separator (for multi-phase demos)."""
    print(f"\n{BOLD}{MAGENTA}{'━' * 62}{RESET}")
    print(f"  {BOLD}Phase {n}{RESET} {DIM}│{RESET} {BOLD}{title}{RESET}")
    if subtitle:
        print(f"         {DIM}{subtitle}{RESET}")
    print(f"{BOLD}{MAGENTA}{'━' * 62}{RESET}\n")


def ok(text: str) -> None:
    print(f"  {CHECK} {text}")


def warn(text: str) -> None:
    print(f"  {WARN} {text}")


def err(text: str) -> None:
    print(f"  {FAIL} {text}")


def info(text: str) -> None:
    print(f"  {DIM}{text}{RESET}")


def progress(text: str) -> None:
    print(f"  {ARROW} {text}", end="", flush=True)


def done(dt: float) -> None:
    print(f" {GREEN}done{RESET} {DIM}({dt:.1f}s){RESET}")


def section(text: str) -> None:
    print(f"\n  {BOLD}{text}{RESET}")


def finale(results: list[str], title: str = "Pipeline Complete") -> None:
    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════╗
║  {title}{' ' * max(0, 59 - len(title))}║
╚══════════════════════════════════════════════════════════════╝{RESET}
""")
    for result in results:
        ok(result)
    print(f"""
  {BOLD}device-use{RESET} — middleware for scientific instruments
  {DIM}Like ROS for robots, but for NMR, microscopes, and more.{RESET}
""")


def simulate_stream(text: str, chunk_size: int = 30, delay: float = 0.02):
    import time
    for i in range(0, len(text), chunk_size):
        time.sleep(delay)
        yield text[i:i + chunk_size]
