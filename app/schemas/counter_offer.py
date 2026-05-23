from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Any, Optional, List


class CreateCounterOfferSchema(BaseModel):
    """Lenient schema — accepts any of the field-name conventions the admin
    panel or backwards-compat clients might send:
      - order_id / orderId
      - revised_price / revisedPrice / counter_price / counterPrice / amended_price
      - device_images / deviceImages
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    order_id: Optional[str] = None
    revised_price: Optional[float] = None
    reason: Optional[str] = None
    device_images: Optional[List[dict]] = None

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        # Build a lookup by lowercased / underscore-normalised key
        import re
        lookup = {}
        for k, v in data.items():
            if not isinstance(k, str):
                continue
            nk = re.sub(r"[-\s]+", "_", k.strip()).lower()
            if nk and nk not in lookup:
                lookup[nk] = v

        aliases = {
            "order_id":      ["order_id", "orderid"],
            "revised_price": ["revised_price", "revisedprice", "counter_price",
                              "counterprice", "amended_price", "amendedprice",
                              "new_price", "newprice", "price"],
            "reason":        ["reason", "comment", "note", "notes"],
            "device_images": ["device_images", "deviceimages", "images"],
        }
        out: dict = {}
        for canonical, variants in aliases.items():
            for v in variants:
                if v in lookup and lookup[v] not in (None, ""):
                    out[canonical] = lookup[v]
                    break
        # Coerce revised_price to float if it arrived as a string
        rp = out.get("revised_price")
        if isinstance(rp, str):
            try:
                out["revised_price"] = float(re.sub(r"[£$€,\s]", "", rp.strip()))
            except ValueError:
                out["revised_price"] = None
        return out


class RespondCounterOfferSchema(BaseModel):
    action: Optional[str] = None  # "accept" or "decline"
    feedback: Optional[str] = None
