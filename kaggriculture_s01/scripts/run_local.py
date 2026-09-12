"""Run the starter agent against the local Kaggriculture simulator."""

from kaggle_environments import make

from kaggriculture_agent import agent


def main() -> None:
    env = make("kaggriculture", debug=True)
    env.run([agent, "random"])

    final_steps = env.steps[-1]
    print("episodes=1")
    for index, step in enumerate(final_steps):
        print(f"player={index} reward={step.reward} status={step.status}")


if __name__ == "__main__":
    main()
