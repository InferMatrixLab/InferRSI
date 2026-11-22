"""Compatibility exports; use :mod:`inferrsi.apps.workflows.skill_eval_engineering`."""

from inferrsi.apps.workflows.skill_eval_engineering import main, verify

__all__ = ['verify', 'main']


if __name__ == "__main__":
    main()
