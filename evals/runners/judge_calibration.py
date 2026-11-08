"""Compute agreement and Cohen's kappa from paired human/judge labels."""

from evals.runners.offline import main as score


def main():
    score("judge_calibration")


if __name__ == "__main__":
    main()
