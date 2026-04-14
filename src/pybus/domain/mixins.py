from typing import TYPE_CHECKING

from .exceptions import BusinessRuleValidationException

if TYPE_CHECKING:
    from .rules import BusinessRule


class BusinessRuleValidationMixin:
    def check_rule(self, rule: "BusinessRule"):
        if rule.is_broken():
            raise BusinessRuleValidationException(rule)
