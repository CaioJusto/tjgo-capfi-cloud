from pydantic import BaseModel


class UploadPlanilhaResponse(BaseModel):
    processes: list[str]
