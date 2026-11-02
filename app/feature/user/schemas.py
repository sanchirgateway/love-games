from pydantic import BaseModel, ConfigDict


class UserShort(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    username: str | None


class UserOut(UserShort):
    last_name: str | None
    timezone: str
    partner_id: int | None


class PairOut(BaseModel):
    partner: UserShort | None  # null — пары ещё нет
    invite_link: str | None  # t.me/<bot>?start=pair_...; только пока пары нет
