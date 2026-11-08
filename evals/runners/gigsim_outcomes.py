"""Aggregate recorded simulator receipts; does not launch a live simulator run."""

from evals.runners.offline import main as score


def main():
    score("gigsim_outcomes")


if __name__ == "__main__":
    main()
