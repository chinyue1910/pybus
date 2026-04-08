from pydantic import BaseModel


class BusinessRule(BaseModel):
    _message: str = "Business rule is broken"

    def get_message(self) -> str:
        return self._message

    def is_broken(self) -> bool: ...
