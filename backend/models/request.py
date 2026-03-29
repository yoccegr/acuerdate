from pydantic import BaseModel, field_validator

from models.internal import UserLocation


class RecommendRequest(BaseModel):
    items: list[str]
    location: UserLocation

    @field_validator("items")
    @classmethod
    def items_not_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("La lista de ítems no puede estar vacía")
        cleaned = [item.strip() for item in v]
        for item in cleaned:
            if not item:
                raise ValueError(
                    "Cada ítem debe contener al menos un carácter no vacío"
                )
        return cleaned
