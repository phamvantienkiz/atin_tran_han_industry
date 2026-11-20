import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from app.api.deps import get_detection_service, get_ws_hub
from app.core.logging import get_logger
from app.schemas.detection import FocusDetectionPayload
from app.services.detection_service import DetectionService
from app.services.ws_hub import DetectionWsHub

logger = get_logger("app.api.v1.detections")
router = APIRouter(prefix="/detections", tags=["detections"])
ws_alias_router = APIRouter(tags=["detections"])


@router.get("")
def get_detections(
    service: Annotated[DetectionService, Depends(get_detection_service)],
    focus_cam_id: str | None = Query(default=None, max_length=64),
) -> dict[str, Any]:
    return service.get_detections(focus_cam_id=focus_cam_id)


@router.post("/focus")
def set_detection_focus(
    payload: FocusDetectionPayload,
    service: Annotated[DetectionService, Depends(get_detection_service)],
) -> dict[str, Any]:
    return service.set_focus(payload.cam_id)


@router.post("/{cam_id}/reset-stats")
def reset_camera_stats(
    cam_id: str,
    service: Annotated[DetectionService, Depends(get_detection_service)],
) -> dict[str, Any]:
    return service.reset_stats(cam_id)


async def _handle_detections_ws(
    websocket: WebSocket,
    service: DetectionService,
    ws_hub: DetectionWsHub,
) -> None:
    await ws_hub.connect(websocket)
    try:
        await websocket.send_json(
            {
                "type": "detections",
                "ts": time.time(),
                "data": service.get_detections(),
            }
        )
        while True:
            msg = await websocket.receive_json()
            if isinstance(msg, dict) and msg.get("type") == "focus":
                cam_id = msg.get("cam_id")
                try:
                    service.set_focus(str(cam_id) if cam_id else None)
                except Exception as exc:  # noqa: BLE001 - ignore invalid cam_id from WS client
                    logger.debug("Ignored invalid WS focus cam_id=%r: %s", cam_id, exc)
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.debug("WS detections connection closed with error: %s", exc)
    finally:
        ws_hub.disconnect(websocket)


@router.websocket("/ws")
async def detections_websocket(
    websocket: WebSocket,
    service: Annotated[DetectionService, Depends(get_detection_service)],
    ws_hub: Annotated[DetectionWsHub, Depends(get_ws_hub)],
) -> None:
    await _handle_detections_ws(websocket, service, ws_hub)


@ws_alias_router.websocket("/ws/detections")
async def detections_websocket_alias(
    websocket: WebSocket,
    service: Annotated[DetectionService, Depends(get_detection_service)],
    ws_hub: Annotated[DetectionWsHub, Depends(get_ws_hub)],
) -> None:
    await _handle_detections_ws(websocket, service, ws_hub)
