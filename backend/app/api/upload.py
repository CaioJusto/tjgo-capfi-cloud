from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.schemas.upload import UploadPlanilhaResponse
from app.services.upload import extract_process_numbers_from_xlsx


router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("/planilha", response_model=UploadPlanilhaResponse)
async def upload_planilha(file: UploadFile = File(...)) -> UploadPlanilhaResponse:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only .xlsx files are supported")

    contents = await file.read()
    processes = extract_process_numbers_from_xlsx(contents)
    if not processes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No process numbers were found in the uploaded spreadsheet",
        )
    return UploadPlanilhaResponse(processes=processes)
