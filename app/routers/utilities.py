from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from app.models.network import Network
from app.models.storage_option import StorageOption
from app.models.device_condition import DeviceCondition
from app.models.brand import Brand
from app.models.category import Category
from app.models.order_status import OrderStatus
from app.models.payment_status import PaymentStatus
from app.schemas.utility import (
    CreateNetworkSchema, UpdateNetworkSchema,
    CreateStorageOptionSchema, UpdateStorageOptionSchema,
    CreateDeviceConditionSchema, UpdateDeviceConditionSchema,
    CreateBrandSchema, UpdateBrandSchema,
    CreateCategorySchema, UpdateCategorySchema,
    CreateOrderStatusSchema, UpdateOrderStatusSchema,
    CreatePaymentStatusSchema, UpdatePaymentStatusSchema,
    ReorderSchema,
)
from app.middleware.auth import get_current_admin
from app.utils.response import success_response, created_response
from app.utils.logger import logger

router = APIRouter(prefix="/utilities", tags=["Utilities"])


# ── GET ALL UTILITIES IN ONE REQUEST (public) ──────────────────────────────────

@router.get("/all", summary="Get all utilities in one request (public)")
async def get_all_utilities():
    storage_opts, conditions, networks, brands, categories, order_statuses, payment_statuses = await _fetch_all()
    return success_response({
        "storageOptions": [_ss(o) for o in storage_opts],
        "deviceConditions": [_sc(c) for c in conditions],
        "networks": [_sn(n) for n in networks],
        "brands": [_sb(b) for b in brands],
        "categories": [_scat(c) for c in categories],
        "orderStatuses": [_sos(s) for s in order_statuses],
        "paymentStatuses": [_sps(s) for s in payment_statuses],
    })


async def _fetch_all():
    from asyncio import gather
    return await gather(
        StorageOption.find().sort(StorageOption.sort_order).to_list(),
        DeviceCondition.find().sort(DeviceCondition.sort_order).to_list(),
        Network.find().sort(Network.sort_order).to_list(),
        Brand.find().sort(Brand.sort_order).to_list(),
        Category.find().sort(Category.sort_order).to_list(),
        OrderStatus.find().sort(OrderStatus.sort_order).to_list(),
        PaymentStatus.find().sort(PaymentStatus.sort_order).to_list(),
    )


# ── STORAGE OPTIONS ───────────────────────────────────────────────────────────

@router.get("/storage", summary="Get all storage options (public)")
@router.get("/storage-options", summary="Get all storage options (public) [alias]")
async def get_storage_options():
    options = await StorageOption.find().sort(StorageOption.sort_order).to_list()
    return success_response({"storageOptions": [_ss(o) for o in options]})


@router.get("/storage/{option_id}", summary="Get storage option by ID", dependencies=[Depends(get_current_admin)])
async def get_storage_option(option_id: str):
    opt = await StorageOption.get(option_id)
    if not opt:
        raise HTTPException(status_code=404, detail="Storage option not found")
    return success_response({"storageOption": _ss(opt)})


@router.post("/storage", summary="Create storage option", dependencies=[Depends(get_current_admin)])
async def create_storage_option(body: CreateStorageOptionSchema):
    opt = StorageOption(**body.dict())
    await opt.insert()
    return created_response({"storageOption": _ss(opt)}, "Storage option created")


@router.put("/storage/{option_id}", summary="Update storage option", dependencies=[Depends(get_current_admin)])
async def update_storage_option(option_id: str, body: UpdateStorageOptionSchema):
    opt = await StorageOption.get(option_id)
    if not opt:
        raise HTTPException(status_code=404, detail="Storage option not found")
    for k, v in body.dict(exclude_unset=True).items():
        setattr(opt, k, v)
    await opt.save()
    return success_response({"storageOption": _ss(opt)}, "Storage option updated")


@router.delete("/storage/{option_id}", summary="Delete storage option", dependencies=[Depends(get_current_admin)])
async def delete_storage_option(option_id: str):
    opt = await StorageOption.get(option_id)
    if not opt:
        raise HTTPException(status_code=404, detail="Storage option not found")
    await opt.delete()
    return success_response({"message": "Storage option deleted"})


@router.post("/storage/reorder", summary="Reorder storage options", dependencies=[Depends(get_current_admin)])
async def reorder_storage_options(body: ReorderSchema):
    for i, item in enumerate(body.items):
        opt = await StorageOption.get(item.id)
        if opt:
            opt.sort_order = item.sort_order if item.sort_order is not None else i + 1
            await opt.save()
    return success_response({"message": "Storage options reordered"})


# ── DEVICE CONDITIONS ─────────────────────────────────────────────────────────

@router.get("/conditions", summary="Get all device conditions (public)")
@router.get("/device-conditions", summary="Get all device conditions (public) [alias]")
async def get_device_conditions():
    conditions = await DeviceCondition.find().sort(DeviceCondition.sort_order).to_list()
    return success_response({"deviceConditions": [_sc(c) for c in conditions]})


@router.get("/conditions/{condition_id}", summary="Get condition by ID", dependencies=[Depends(get_current_admin)])
async def get_condition(condition_id: str):
    c = await DeviceCondition.get(condition_id)
    if not c:
        raise HTTPException(status_code=404, detail="Condition not found")
    return success_response({"condition": _sc(c)})


@router.post("/conditions", summary="Create device condition", dependencies=[Depends(get_current_admin)])
async def create_device_condition(body: CreateDeviceConditionSchema):
    cond = DeviceCondition(**body.dict())
    await cond.insert()
    return created_response({"condition": _sc(cond)}, "Device condition created")


@router.put("/conditions/{condition_id}", summary="Update device condition", dependencies=[Depends(get_current_admin)])
async def update_device_condition(condition_id: str, body: UpdateDeviceConditionSchema):
    c = await DeviceCondition.get(condition_id)
    if not c:
        raise HTTPException(status_code=404, detail="Condition not found")
    for k, v in body.dict(exclude_unset=True).items():
        setattr(c, k, v)
    await c.save()
    return success_response({"condition": _sc(c)}, "Condition updated")


@router.delete("/conditions/{condition_id}", summary="Delete condition", dependencies=[Depends(get_current_admin)])
async def delete_condition(condition_id: str):
    c = await DeviceCondition.get(condition_id)
    if not c:
        raise HTTPException(status_code=404, detail="Condition not found")
    await c.delete()
    return success_response({"message": "Condition deleted"})


@router.post("/conditions/reorder", summary="Reorder device conditions", dependencies=[Depends(get_current_admin)])
async def reorder_conditions(body: ReorderSchema):
    for i, item in enumerate(body.items):
        c = await DeviceCondition.get(item.id)
        if c:
            c.sort_order = item.sort_order if item.sort_order is not None else i + 1
            await c.save()
    return success_response({"message": "Conditions reordered"})


# ── NETWORKS ──────────────────────────────────────────────────────────────────

@router.get("/networks", summary="Get all networks (public)")
async def get_networks():
    networks = await Network.find().sort(Network.sort_order).to_list()
    return success_response({"networks": [_sn(n) for n in networks]})


@router.get("/networks/{network_id}", summary="Get network by ID", dependencies=[Depends(get_current_admin)])
async def get_network(network_id: str):
    n = await Network.get(network_id)
    if not n:
        raise HTTPException(status_code=404, detail="Network not found")
    return success_response({"network": _sn(n)})


@router.post("/networks", summary="Create network", dependencies=[Depends(get_current_admin)])
async def create_network(body: CreateNetworkSchema):
    network = Network(**body.dict())
    await network.insert()
    return created_response({"network": _sn(network)}, "Network created")


@router.put("/networks/{network_id}", summary="Update network", dependencies=[Depends(get_current_admin)])
async def update_network(network_id: str, body: UpdateNetworkSchema):
    network = await Network.get(network_id)
    if not network:
        raise HTTPException(status_code=404, detail="Network not found")
    for k, v in body.dict(exclude_unset=True).items():
        setattr(network, k, v)
    await network.save()
    return success_response({"network": _sn(network)}, "Network updated")


@router.delete("/networks/{network_id}", summary="Delete network", dependencies=[Depends(get_current_admin)])
async def delete_network(network_id: str):
    n = await Network.get(network_id)
    if not n:
        raise HTTPException(status_code=404, detail="Network not found")
    await n.delete()
    return success_response({"message": "Network deleted"})


@router.post("/networks/reorder", summary="Reorder networks", dependencies=[Depends(get_current_admin)])
async def reorder_networks(body: ReorderSchema):
    for i, item in enumerate(body.items):
        n = await Network.get(item.id)
        if n:
            n.sort_order = item.sort_order if item.sort_order is not None else i + 1
            await n.save()
    return success_response({"message": "Networks reordered"})


# ── BRANDS ────────────────────────────────────────────────────────────────────

@router.get("/brands", summary="Get all brands (public)")
async def get_brands():
    brands = await Brand.find().sort(Brand.sort_order).to_list()
    return success_response({"brands": [_sb(b) for b in brands]})


@router.get("/brands/{brand_id}", summary="Get brand by ID", dependencies=[Depends(get_current_admin)])
async def get_brand(brand_id: str):
    b = await Brand.get(brand_id)
    if not b:
        raise HTTPException(status_code=404, detail="Brand not found")
    return success_response({"brand": _sb(b)})


@router.post("/brands", summary="Create brand", dependencies=[Depends(get_current_admin)])
async def create_brand(body: CreateBrandSchema):
    brand = Brand(**body.dict())
    await brand.insert()
    logger.info(f"Brand created: {brand.name}")
    return created_response({"brand": _sb(brand)}, "Brand created")


@router.put("/brands/{brand_id}", summary="Update brand", dependencies=[Depends(get_current_admin)])
async def update_brand(brand_id: str, body: UpdateBrandSchema):
    b = await Brand.get(brand_id)
    if not b:
        raise HTTPException(status_code=404, detail="Brand not found")
    for k, v in body.dict(exclude_unset=True).items():
        setattr(b, k, v)
    b.updated_at = datetime.utcnow()
    await b.save()
    return success_response({"brand": _sb(b)}, "Brand updated")


@router.delete("/brands/{brand_id}", summary="Delete brand", dependencies=[Depends(get_current_admin)])
async def delete_brand(brand_id: str):
    b = await Brand.get(brand_id)
    if not b:
        raise HTTPException(status_code=404, detail="Brand not found")
    await b.delete()
    return success_response({"message": "Brand deleted"})


@router.post("/brands/reorder", summary="Reorder brands", dependencies=[Depends(get_current_admin)])
async def reorder_brands(body: ReorderSchema):
    for i, item in enumerate(body.items):
        b = await Brand.get(item.id)
        if b:
            b.sort_order = item.sort_order if item.sort_order is not None else i + 1
            await b.save()
    return success_response({"message": "Brands reordered"})


# ── CATEGORIES ────────────────────────────────────────────────────────────────

@router.get("/categories", summary="Get all categories (public)")
async def get_categories():
    categories = await Category.find().sort(Category.sort_order).to_list()
    return success_response({"categories": [_scat(c) for c in categories]})


@router.get("/categories/{category_id}", summary="Get category by ID", dependencies=[Depends(get_current_admin)])
async def get_category(category_id: str):
    c = await Category.get(category_id)
    if not c:
        raise HTTPException(status_code=404, detail="Category not found")
    return success_response({"category": _scat(c)})


@router.post("/categories", summary="Create category", dependencies=[Depends(get_current_admin)])
async def create_category(body: CreateCategorySchema):
    cat = Category(**body.dict())
    await cat.insert()
    return created_response({"category": _scat(cat)}, "Category created")


@router.put("/categories/{category_id}", summary="Update category", dependencies=[Depends(get_current_admin)])
async def update_category(category_id: str, body: UpdateCategorySchema):
    c = await Category.get(category_id)
    if not c:
        raise HTTPException(status_code=404, detail="Category not found")
    for k, v in body.dict(exclude_unset=True).items():
        setattr(c, k, v)
    c.updated_at = datetime.utcnow()
    await c.save()
    return success_response({"category": _scat(c)}, "Category updated")


@router.delete("/categories/{category_id}", summary="Delete category", dependencies=[Depends(get_current_admin)])
async def delete_category(category_id: str):
    c = await Category.get(category_id)
    if not c:
        raise HTTPException(status_code=404, detail="Category not found")
    await c.delete()
    return success_response({"message": "Category deleted"})


@router.post("/categories/reorder", summary="Reorder categories", dependencies=[Depends(get_current_admin)])
async def reorder_categories(body: ReorderSchema):
    for i, item in enumerate(body.items):
        c = await Category.get(item.id)
        if c:
            c.sort_order = item.sort_order if item.sort_order is not None else i + 1
            await c.save()
    return success_response({"message": "Categories reordered"})


# ── ORDER STATUSES ────────────────────────────────────────────────────────────

@router.get("/order-statuses", summary="Get all order statuses", dependencies=[Depends(get_current_admin)])
async def get_order_statuses():
    statuses = await OrderStatus.find().sort(OrderStatus.sort_order).to_list()
    return success_response({"orderStatuses": [_sos(s) for s in statuses]})


@router.get("/order-statuses/{status_id}", summary="Get order status by ID", dependencies=[Depends(get_current_admin)])
async def get_order_status(status_id: str):
    s = await OrderStatus.get(status_id)
    if not s:
        raise HTTPException(status_code=404, detail="Order status not found")
    return success_response({"orderStatus": _sos(s)})


@router.post("/order-statuses", summary="Create order status", dependencies=[Depends(get_current_admin)])
async def create_order_status(body: CreateOrderStatusSchema):
    s = OrderStatus(**body.dict())
    await s.insert()
    return created_response({"orderStatus": _sos(s)}, "Order status created")


@router.put("/order-statuses/{status_id}", summary="Update order status", dependencies=[Depends(get_current_admin)])
async def update_order_status(status_id: str, body: UpdateOrderStatusSchema):
    s = await OrderStatus.get(status_id)
    if not s:
        raise HTTPException(status_code=404, detail="Order status not found")
    for k, v in body.dict(exclude_unset=True).items():
        setattr(s, k, v)
    s.updated_at = datetime.utcnow()
    await s.save()
    return success_response({"orderStatus": _sos(s)}, "Order status updated")


@router.delete("/order-statuses/{status_id}", summary="Delete order status", dependencies=[Depends(get_current_admin)])
async def delete_order_status(status_id: str):
    s = await OrderStatus.get(status_id)
    if not s:
        raise HTTPException(status_code=404, detail="Order status not found")
    await s.delete()
    return success_response({"message": "Order status deleted"})


@router.post("/order-statuses/reorder", summary="Reorder order statuses", dependencies=[Depends(get_current_admin)])
async def reorder_order_statuses(body: ReorderSchema):
    for i, item in enumerate(body.items):
        s = await OrderStatus.get(item.id)
        if s:
            s.sort_order = item.sort_order if item.sort_order is not None else i + 1
            await s.save()
    return success_response({"message": "Order statuses reordered"})


# ── PAYMENT STATUSES ──────────────────────────────────────────────────────────

@router.get("/payment-statuses", summary="Get all payment statuses", dependencies=[Depends(get_current_admin)])
async def get_payment_statuses():
    statuses = await PaymentStatus.find().sort(PaymentStatus.sort_order).to_list()
    return success_response({"paymentStatuses": [_sps(s) for s in statuses]})


@router.get("/payment-statuses/{status_id}", summary="Get payment status by ID", dependencies=[Depends(get_current_admin)])
async def get_payment_status(status_id: str):
    s = await PaymentStatus.get(status_id)
    if not s:
        raise HTTPException(status_code=404, detail="Payment status not found")
    return success_response({"paymentStatus": _sps(s)})


@router.post("/payment-statuses", summary="Create payment status", dependencies=[Depends(get_current_admin)])
async def create_payment_status(body: CreatePaymentStatusSchema):
    s = PaymentStatus(**body.dict())
    await s.insert()
    return created_response({"paymentStatus": _sps(s)}, "Payment status created")


@router.put("/payment-statuses/{status_id}", summary="Update payment status", dependencies=[Depends(get_current_admin)])
async def update_payment_status(status_id: str, body: UpdatePaymentStatusSchema):
    s = await PaymentStatus.get(status_id)
    if not s:
        raise HTTPException(status_code=404, detail="Payment status not found")
    for k, v in body.dict(exclude_unset=True).items():
        setattr(s, k, v)
    s.updated_at = datetime.utcnow()
    await s.save()
    return success_response({"paymentStatus": _sps(s)}, "Payment status updated")


@router.delete("/payment-statuses/{status_id}", summary="Delete payment status", dependencies=[Depends(get_current_admin)])
async def delete_payment_status(status_id: str):
    s = await PaymentStatus.get(status_id)
    if not s:
        raise HTTPException(status_code=404, detail="Payment status not found")
    await s.delete()
    return success_response({"message": "Payment status deleted"})


@router.post("/payment-statuses/reorder", summary="Reorder payment statuses", dependencies=[Depends(get_current_admin)])
async def reorder_payment_statuses(body: ReorderSchema):
    for i, item in enumerate(body.items):
        s = await PaymentStatus.get(item.id)
        if s:
            s.sort_order = item.sort_order if item.sort_order is not None else i + 1
            await s.save()
    return success_response({"message": "Payment statuses reordered"})


# ── SERIALIZERS ───────────────────────────────────────────────────────────────

def _sn(n: Network) -> dict:
    return {
        "id": str(n.id), "_id": str(n.id),
        "name": n.name, "value": n.value,
        "is_active": n.is_active, "isActive": n.is_active,
        "sort_order": n.sort_order, "sortOrder": n.sort_order,
    }


def _ss(o: StorageOption) -> dict:
    return {
        "id": str(o.id), "_id": str(o.id),
        "name": o.name, "value": o.value,
        "is_active": o.is_active, "isActive": o.is_active,
        "sort_order": o.sort_order, "sortOrder": o.sort_order,
    }


def _sc(c: DeviceCondition) -> dict:
    return {
        "id": str(c.id), "_id": str(c.id),
        "name": c.name, "value": c.value,
        "description": c.description,
        "is_active": c.is_active, "isActive": c.is_active,
        "sort_order": getattr(c, "sort_order", 0), "sortOrder": getattr(c, "sort_order", 0),
    }


def _sb(b: Brand) -> dict:
    return {
        "id": str(b.id), "_id": str(b.id),
        "name": b.name, "logo": b.logo,
        "is_active": b.is_active, "isActive": b.is_active,
        "sort_order": b.sort_order, "sortOrder": b.sort_order,
        "created_at": b.created_at.isoformat(), "createdAt": b.created_at.isoformat(),
    }


def _scat(c: Category) -> dict:
    return {
        "id": str(c.id), "_id": str(c.id),
        "name": c.name, "description": c.description,
        "is_active": c.is_active, "isActive": c.is_active,
        "sort_order": c.sort_order, "sortOrder": c.sort_order,
        "created_at": c.created_at.isoformat(), "createdAt": c.created_at.isoformat(),
    }


def _sos(s: OrderStatus) -> dict:
    return {
        "id": str(s.id), "_id": str(s.id),
        "name": s.name, "value": s.value, "color": s.color,
        "is_active": s.is_active, "isActive": s.is_active,
        "sort_order": s.sort_order, "sortOrder": s.sort_order,
        "created_at": s.created_at.isoformat(), "createdAt": s.created_at.isoformat(),
    }


def _sps(s: PaymentStatus) -> dict:
    return {
        "id": str(s.id), "_id": str(s.id),
        "name": s.name, "value": s.value, "color": s.color,
        "is_active": s.is_active, "isActive": s.is_active,
        "sort_order": s.sort_order, "sortOrder": s.sort_order,
        "created_at": s.created_at.isoformat(), "createdAt": s.created_at.isoformat(),
    }
