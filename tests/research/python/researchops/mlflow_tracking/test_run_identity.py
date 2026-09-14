from research.python.researchops.mlflow_tracking.run_identity import tracking_key


def test_tracking_key_is_stable_and_model_specific(training_release_package):
    manifest = training_release_package.manifest
    first = tracking_key(manifest, model_name="logistic_regression")
    second = tracking_key(manifest, model_name="logistic_regression")
    other = tracking_key(manifest, model_name="random_forest")
    assert first == second
    assert first != other
    assert len(first) == 64
