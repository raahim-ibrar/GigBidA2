"""Score recorded ReAct, supervisor and hand-built graph conditions."""

from evals.runners.comparison import main as compare


def main():
    compare("orchestration_compare")


if __name__ == "__main__":
    main()
