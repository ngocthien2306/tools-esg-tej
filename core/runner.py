from linearmodels.panel import PanelOLS


def fit_panel(y, X, entity_effects: bool = False, time_effects: bool = True,
              cluster_entity: bool = True):
    res = PanelOLS(
        y, X,
        entity_effects=entity_effects,
        time_effects=time_effects,
    ).fit(
        cov_type="clustered" if cluster_entity else "robust",
        cluster_entity=cluster_entity,
    )
    return res
