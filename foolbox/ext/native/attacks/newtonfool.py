from typing import Union, Tuple
import eagerpy as ep

from ..models import Model

from ..criteria import Misclassification

from ..devutils import atleast_kd, flatten

from .base import MinimizationAttack
from .base import get_criterion
from .base import T


class NewtonFoolAttack(MinimizationAttack):
    """NewtonFool Attack introduced in [1]_

    References
    ----------
    .. [1] Uyeong Jang et al., "Objective Metrics and Gradient Descent
           Algorithms for Adversarial Examples in Machine Learning",
           https://dl.acm.org/citation.cfm?id=3134635
    """

    def __init__(self, steps: int = 100, stepsize: float = 0.01):
        self.steps = steps
        self.stepsize = stepsize

    def __call__(
        self, model: Model, inputs: T, criterion: Union[Misclassification, T]
    ) -> T:

        x, restore_type = ep.astensor_(inputs)
        criterion_ = get_criterion(criterion)
        del inputs, criterion

        N = len(x)

        if isinstance(criterion_, Misclassification):
            classes = criterion_.labels
        else:
            raise ValueError("unsupported criterion")

        if classes.shape != (N,):
            raise ValueError(
                f"expected labels to have shape ({N},), got {classes.shape}"
            )

        min_, max_ = model.bounds

        x_l2_norm = flatten(x.square()).sum(1)

        def loss_fun(x: ep.Tensor) -> Tuple[ep.Tensor, Tuple[ep.Tensor, ep.Tensor]]:
            logits = model(x)
            scores = ep.softmax(logits)
            pred_scores = scores[range(N), classes]
            loss = pred_scores.sum()
            return loss, (scores, pred_scores)

        for i in range(self.steps):
            # (1) get the scores and gradients
            _, (scores, pred_scores), gradients = ep.value_aux_and_grad(loss_fun, x)

            pred = scores.argmax(-1)
            num_classes = scores.shape[-1]

            # (2) calculate gradient norm
            gradients_l2_norm = flatten(gradients.square()).sum(1)

            # (3) calculate delta
            a = self.stepsize * x_l2_norm * gradients_l2_norm
            b = pred_scores - 1.0 / num_classes

            delta = ep.minimum(a, b)

            # (4) stop the attack if an adversarial example has been found
            # this is not described in the paper but otherwise once the prob. drops
            # below chance level the likelihood is not decreased but increased
            is_not_adversarial = (pred == classes).float32()
            delta *= is_not_adversarial

            # (5) calculate & apply current perturbation
            a = atleast_kd(delta / gradients_l2_norm.square(), gradients.ndim)
            x -= a * gradients

            x = ep.clip(x, min_, max_)

        return restore_type(x)
