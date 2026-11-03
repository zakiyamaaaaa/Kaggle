from kaggriculture_agent.cnn_ppo import CHANNELS, SCALARS, THRESHOLDS, encode_observation, policy_value
from test_macro_rl import observation


def test_encoder_and_forward_schema():
    obs = observation()
    image, scalars = encode_observation(obs)
    assert (len(image), len(image[0]), len(image[0][0])) == (10, 10, len(CHANNELS))
    assert len(scalars) == len(SCALARS)
    filters, hidden = 2, 3
    model = {
        "conv": {"weights": [[[[0.0] * 3 for _ in range(3)] for _ in CHANNELS] for _ in range(filters)], "bias": [0.0] * filters},
        "hidden": {"weights": [[0.0] * (filters + len(SCALARS)) for _ in range(hidden)], "bias": [0.0] * hidden},
        "policy": {"weights": [[0.0] * hidden for _ in THRESHOLDS], "bias": list(range(len(THRESHOLDS)))},
        "value": {"weights": [0.0] * hidden, "bias": 1.25},
    }
    probs, value = policy_value(model, image, scalars)
    assert abs(sum(probs) - 1.0) < 1e-9
    assert probs[-1] == max(probs)
    assert value == 1.25
