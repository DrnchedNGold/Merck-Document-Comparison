"""Launch the desktop shell: ``python -m desktop``."""

from desktop.main_window import MerckDesktopApp


def main() -> None:
    app = MerckDesktopApp()
    app.mainloop()


if __name__ == "__main__":
    main()
