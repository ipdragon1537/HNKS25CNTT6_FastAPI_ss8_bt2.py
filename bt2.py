from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import List, Optional
import re
app = FastAPI()
assets_db = [
    {"id": 1, "serial_number": "SN-MAC-01", "model": "MacBook Pro M3", "stock_available": 5, "status": "READY"},
    {"id": 2, "serial_number": "SN-DELL-02", "model": "Dell UltraSharp 27", "stock_available": 10, "status": "READY"},
    {"id": 3, "serial_number": "SN-THINK-03", "model": "ThinkPad X1 Carbon", "stock_available": 0, "status": "REPAIRING"}
]

allocations_db = [
    {
        "id": 1,
        "asset_id": 1,
        "employee_email": "dev.nguyen@company.com",
        "allocated_quantity": 1,
        "start_date": "2026-07-01",
        "duration_months": 12
    }
]
asset_id_counter = 4
allocation_id_counter = 2
class AssetCreate(BaseModel):
    serial_number: str = Field(..., description="Mã thiết bị duy nhất")
    model: str = Field(..., min_length=2, max_length=255, description="Tên dòng máy/thiết bị")
    stock_available: int = Field(..., ge=0, description="Số lượng tồn kho khả dụng")
    status: str = Field(..., description="READY, ALLOCATED, REPAIRING, SCRAPPED")
    @field_validator('status')
    def validate_status(cls, v):
        allowed = ["READY", "ALLOCATED", "REPAIRING", "SCRAPPED"]
        if v not in allowed:
            raise ValueError(f"Status phải thuộc một trong các giá trị: {allowed}")
        return v
class AssetUpdate(BaseModel):
    serial_number: Optional[str] = Field(None)
    model: Optional[str] = Field(None, min_length=2, max_length=255)
    stock_available: Optional[int] = Field(None, ge=0)
    status: Optional[str] = Field(None)
    @field_validator('status')
    def validate_status(cls, v):
        if v is not None:
            allowed = ["READY", "ALLOCATED", "REPAIRING", "SCRAPPED"]
            if v not in allowed:
                raise ValueError(f"Status phải thuộc một trong các giá trị: {allowed}")
        return v
class AllocationCreate(BaseModel):
    asset_id: int
    employee_email: str
    allocated_quantity: int = Field(..., gt=0, description="Số lượng cấp phát phải lớn hơn 0")
    start_date: str = Field(..., description="Định dạng YYYY-MM-DD")
    duration_months: int = Field(..., ge=1, le=12, description="Thời gian mượn từ 1 đến 12 tháng")
    @field_validator('employee_email')
    def validate_email_regex(cls, v):
        email_regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        if not re.match(email_regex, v):
            raise ValueError("Định dạng email của nhân viên không hợp lệ.")
        return v
@app.post("/assets", status_code=status.HTTP_201_CREATED, tags=["Assets"])
def create_asset(asset: AssetCreate):
    global asset_id_counter
    if any(a["serial_number"] == asset.serial_number for a in assets_db):
        raise HTTPException(status_code=400, detail="Serial number đã tồn tại trên hệ thống.")
    new_asset = asset.dict()
    new_asset["id"] = asset_id_counter
    assets_db.append(new_asset)
    asset_id_counter += 1
    return new_asset
@app.get("/assets", tags=["Assets"])
def get_assets(
    keyword: Optional[str] = Query(None, description="Tìm theo serial_number hoặc model"),
    status: Optional[str] = Query(None, description="Lọc theo trạng thái thiết bị"),
    min_stock: Optional[int] = Query(None, description="Số lượng tồn kho tối thiểu")
):
    filtered_assets = assets_db
    if status:
        filtered_assets = [a for a in filtered_assets if a["status"].upper() == status.upper()]
    if min_stock is not None:
        filtered_assets = [a for a in filtered_assets if a["stock_available"] >= min_stock]
    if keyword:
        try:
            pattern = re.compile(keyword, re.IGNORECASE)
            filtered_assets = [
                a for a in filtered_assets 
                if pattern.search(a["serial_number"]) or pattern.search(a["model"])
            ]
        except re.error:
            raise HTTPException(status_code=400, detail="Keyword Regex Pattern không đúng định dạng.")
    return filtered_assets
@app.get("/assets/{asset_id}", tags=["Assets"])
def get_asset_by_id(asset_id: int):
    asset = next((a for a in assets_db if a["id"] == asset_id), None)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset
@app.put("/assets/{asset_id}", tags=["Assets"])
def update_asset(asset_id: int, payload: AssetUpdate):
    asset = next((a for a in assets_db if a["id"] == asset_id), None)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    update_data = payload.dict(exclude_unset=True)
    if "serial_number" in update_data:
        if any(a["serial_number"] == update_data["serial_number"] and a["id"] != asset_id for a in assets_db):
            raise HTTPException(status_code=400, detail="Serial number đã tồn tại trên thiết bị khác.")
            
    asset.update(update_data)
    return asset
@app.delete("/assets/{asset_id}", tags=["Assets"])
def delete_asset(asset_id: int):
    global assets_db
    asset = next((a for a in assets_db if a["id"] == asset_id), None)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    assets_db = [a for a in assets_db if a["id"] != asset_id]
    return {"message": f"Xóa tài sản ID {asset_id} thành công."}
@app.post("/allocations", status_code=status.HTTP_201_CREATED, tags=["Allocations"])
def create_allocation(alloc: AllocationCreate):
    global allocation_id_counter
    asset = next((a for a in assets_db if a["id"] == alloc.asset_id), None)
    if not asset:
        raise HTTPException(status_code=400, detail="Mã tài sản (asset_id) không tồn tại trong hệ thống công ty.")
    if asset["status"] != "READY":
        raise HTTPException(
            status_code=400, 
            detail=f"Thiết bị đang ở trạng thái '{asset['status']}', không thể bàn giao (Chỉ chấp nhận 'READY')."
        )
    if alloc.allocated_quantity > asset["stock_available"]:
        raise HTTPException(
            status_code=400, 
            detail=f"Số lượng yêu cầu ({alloc.allocated_quantity}) vượt quá tồn kho khả dụng hiện tại ({asset['stock_available']})."
        )
    asset["stock_available"] -= alloc.allocated_quantity
    if asset["stock_available"] == 0:
        asset["status"] = "ALLOCATED"
    new_alloc = alloc.dict()
    new_alloc["id"] = allocation_id_counter
    allocations_db.append(new_alloc)
    allocation_id_counter += 1
    return {
        "message": "Cấp phát tài sản thiết bị thành công!",
        "allocation": new_alloc,
        "updated_asset": asset
    }
@app.get("/allocations", tags=["Allocations"])
def get_allocations():
    return allocations_db