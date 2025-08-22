#!/usr/bin/env python

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, List
import asyncio
import logging
import time
import uuid
from enum import Enum
from robot_inference import RobotInferenceManager
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Robot Control API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class BoxColor(str, Enum):
    WHITE = "white"
    YELLOW = "yellow"
    BLACK = "black"


class RobotStatus(str, Enum):
    IDLE = "idle"
    LOADING_MODEL = "loading_model"
    PICKING = "picking"
    ERROR = "error"


class Order(BaseModel):
    id: str
    white_boxes: int
    yellow_boxes: int
    black_boxes: int = 0
    completed_white: int = 0
    completed_yellow: int = 0
    completed_black: int = 0
    status: str = "pending"
    created_at: float = None

    def __init__(self, **data):
        super().__init__(**data)
        if self.created_at is None:
            self.created_at = time.time()


class PickRequest(BaseModel):
    color: BoxColor
    order_id: Optional[str] = None


class CreateOrderRequest(BaseModel):
    white_boxes: int
    yellow_boxes: int
    black_boxes: int = 0


class RobotController:
    def __init__(self):
        # Initialize robot config - modify based on your actual robot
        robot_config = self._get_robot_config()
        self.inference_manager = RobotInferenceManager(robot_config)
        
        self.status = RobotStatus.IDLE
        self.orders: Dict[str, Order] = {}
        self.current_order_id: Optional[str] = None
        self.websocket_connections: List[WebSocket] = []
        self.pick_duration_s = float(os.getenv("PICK_DURATION_S", "10.0"))
        self.pick_fps = int(os.getenv("PICK_FPS", "30"))
    
    def _get_robot_config(self):
        """Get robot configuration from environment or use defaults"""
        # Check if we should use a real robot
        use_real_robot = os.getenv("USE_REAL_ROBOT", "false").lower() == "true"
        
        if not use_real_robot:
            logger.info("Running in simulation mode (USE_REAL_ROBOT=false)")
            return None
        
        logger.info("Attempting to connect to real SO100 robot...")
        
        # Hardcoded SO100 configuration
        robot_port = os.getenv("ROBOT_PORT", "/dev/ttyACM0")
        
        logger.info(f"SO100 robot port: {robot_port}")
        
        # Camera configuration - REQUIRED for SO100
        cameras_config = {
            "front": {
                "index_or_path": os.getenv("CAMERA_FRONT", "/dev/video4"),
                "width": 640,
                "height": 480,
                "fps": 30
            },
            "wrist": {
                "index_or_path": os.getenv("CAMERA_WRIST", "/dev/video6"),
                "width": 640,
                "height": 480,
                "fps": 30
            }
        }
        logger.info(f"Cameras configured - front: {cameras_config['front']['index_or_path']}, wrist: {cameras_config['wrist']['index_or_path']}")
        
        return {
            "port": robot_port,
            "cameras": cameras_config,
            "id": os.getenv("ROBOT_ID", "andrej")  # Use andrej as default ID
        }
    
    async def add_order(self, order: Order):
        self.orders[order.id] = order
        await self.broadcast_status()
    
    async def pick_box(self, color: BoxColor, order_id: Optional[str] = None):
        if self.status != RobotStatus.IDLE:
            raise HTTPException(status_code=400, detail="Robot is busy")
        
        self.status = RobotStatus.LOADING_MODEL
        self.current_order_id = order_id
        await self.broadcast_status()
        
        try:
            # Load model (this happens synchronously but quickly)
            self.inference_manager.load_model(color.value)
            
            self.status = RobotStatus.PICKING
            await self.broadcast_status()
            
            # Execute pick operation in a separate thread to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self.inference_manager.execute_pick,
                color.value,
                self.pick_duration_s,
                self.pick_fps,
                False  # use_amp
            )
            
            # Update order if successful
            if result["success"] and order_id and order_id in self.orders:
                order = self.orders[order_id]
                if color == BoxColor.WHITE:
                    order.completed_white += 1
                elif color == BoxColor.YELLOW:
                    order.completed_yellow += 1
                elif color == BoxColor.BLACK:
                    order.completed_black += 1
                
                # Check if order is complete
                if (order.completed_white >= order.white_boxes and 
                    order.completed_yellow >= order.yellow_boxes and
                    order.completed_black >= order.black_boxes):
                    order.status = "completed"
                else:
                    order.status = "in_progress"
            
            self.status = RobotStatus.IDLE
            await self.broadcast_status()
            
            return result
            
        except Exception as e:
            logger.error(f"Error during pick operation: {e}")
            self.status = RobotStatus.ERROR
            await self.broadcast_status()
            raise HTTPException(status_code=500, detail=str(e))
    
    async def broadcast_status(self):
        status_data = {
            "robot_status": self.status.value,
            "current_model": self.inference_manager.current_color,
            "orders": [order.dict() for order in self.orders.values()],
            "current_order_id": self.current_order_id
        }
        
        disconnected = []
        for websocket in self.websocket_connections:
            try:
                await websocket.send_json(status_data)
            except:
                disconnected.append(websocket)
        
        # Remove disconnected websockets
        for ws in disconnected:
            self.websocket_connections.remove(ws)
    
    async def add_websocket(self, websocket: WebSocket):
        await websocket.accept()
        self.websocket_connections.append(websocket)
        await self.broadcast_status()
    
    def remove_websocket(self, websocket: WebSocket):
        if websocket in self.websocket_connections:
            self.websocket_connections.remove(websocket)
    
    def cleanup(self):
        """Clean up resources on shutdown"""
        self.inference_manager.cleanup()


# Initialize controller
robot_controller = RobotController()


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources when shutting down"""
    robot_controller.cleanup()


@app.get("/")
async def root():
    return {
        "status": "Robot Control API is running",
        "mode": "real" if robot_controller.inference_manager.robot else "simulation"
    }


@app.post("/api/orders")
async def create_order(request: CreateOrderRequest):
    order = Order(
        id=str(uuid.uuid4()),
        white_boxes=request.white_boxes,
        yellow_boxes=request.yellow_boxes,
        black_boxes=request.black_boxes
    )
    await robot_controller.add_order(order)
    return order


@app.get("/api/orders")
async def get_orders():
    return list(robot_controller.orders.values())


@app.post("/api/pick")
async def pick_box(request: PickRequest):
    result = await robot_controller.pick_box(request.color, request.order_id)
    return result


@app.get("/api/status")
async def get_status():
    return {
        "robot_status": robot_controller.status.value,
        "current_model": robot_controller.inference_manager.current_color,
        "orders": list(robot_controller.orders.values()),
        "robot_connected": robot_controller.inference_manager.robot is not None
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await robot_controller.add_websocket(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        robot_controller.remove_websocket(websocket)


@app.delete("/api/orders/{order_id}")
async def delete_order(order_id: str):
    if order_id in robot_controller.orders:
        del robot_controller.orders[order_id]
        await robot_controller.broadcast_status()
        return {"message": "Order deleted"}
    raise HTTPException(status_code=404, detail="Order not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)