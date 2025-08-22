#!/usr/bin/env python

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, List
import asyncio
import logging
import torch
import gc
import time
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

from lerobot.policies.factory import make_policy
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.configs.policies import PreTrainedConfig
from lerobot.utils.utils import get_safe_torch_device
from lerobot.utils.control_utils import predict_action
from lerobot.datasets.utils import build_dataset_frame

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


class RobotStatus(str, Enum):
    IDLE = "idle"
    LOADING_MODEL = "loading_model"
    PICKING = "picking"
    ERROR = "error"


class Order(BaseModel):
    id: str
    white_boxes: int
    yellow_boxes: int
    completed_white: int = 0
    completed_yellow: int = 0
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


class ModelManager:
    def __init__(self):
        self.current_model = None
        self.current_color = None
        self.policy = None
        self.dataset = None
        self.device = None
        self.models = {
            BoxColor.WHITE: "JaspervanLeuven/pick_white_cube",
            BoxColor.YELLOW: "JaspervanLeuven/pick_yellow_cube",
        }
        
    async def load_model(self, color: BoxColor):
        if self.current_color == color and self.policy is not None:
            logger.info(f"Model for {color} already loaded")
            return
        
        logger.info(f"Loading model for {color} boxes")
        
        self.unload_current_model()
        
        model_path = self.models[color]
        
        try:
            self.dataset = LeRobotDataset(
                repo_id=model_path,
                root=None,
            )
            
            policy_config = PreTrainedConfig.from_pretrained(model_path)
            policy_config.pretrained_path = model_path
            
            self.policy = make_policy(policy_config, ds_meta=self.dataset.meta)
            self.device = get_safe_torch_device(policy_config.device)
            
            self.policy.reset()
            self.current_color = color
            
            logger.info(f"Successfully loaded model for {color} boxes")
            
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to load model: {str(e)}")
    
    def unload_current_model(self):
        if self.policy is not None:
            logger.info(f"Unloading current model ({self.current_color})")
            del self.policy
            self.policy = None
            
        if self.dataset is not None:
            del self.dataset
            self.dataset = None
            
        self.current_color = None
        
        torch.cuda.empty_cache()
        gc.collect()
        
        logger.info("GPU memory cleared")
    
    async def execute_pick(self, color: BoxColor):
        await self.load_model(color)
        
        logger.info(f"Executing pick for {color} box")
        
        task = f"Pick the {color} box"
        
        await asyncio.sleep(2)
        
        return {
            "success": True,
            "color": color,
            "timestamp": time.time()
        }


class RobotController:
    def __init__(self):
        self.model_manager = ModelManager()
        self.status = RobotStatus.IDLE
        self.orders: Dict[str, Order] = {}
        self.current_order_id: Optional[str] = None
        self.websocket_connections: List[WebSocket] = []
        
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
            await self.model_manager.load_model(color)
            
            self.status = RobotStatus.PICKING
            await self.broadcast_status()
            
            result = await self.model_manager.execute_pick(color)
            
            if order_id and order_id in self.orders:
                order = self.orders[order_id]
                if color == BoxColor.WHITE:
                    order.completed_white += 1
                else:
                    order.completed_yellow += 1
                
                if (order.completed_white >= order.white_boxes and 
                    order.completed_yellow >= order.yellow_boxes):
                    order.status = "completed"
                else:
                    order.status = "in_progress"
            
            self.status = RobotStatus.IDLE
            await self.broadcast_status()
            
            return result
            
        except Exception as e:
            self.status = RobotStatus.ERROR
            await self.broadcast_status()
            raise e
    
    async def broadcast_status(self):
        status_data = {
            "robot_status": self.status,
            "current_model": self.model_manager.current_color,
            "orders": [order.dict() for order in self.orders.values()],
            "current_order_id": self.current_order_id
        }
        
        for websocket in self.websocket_connections:
            try:
                await websocket.send_json(status_data)
            except:
                pass
    
    async def add_websocket(self, websocket: WebSocket):
        await websocket.accept()
        self.websocket_connections.append(websocket)
        await self.broadcast_status()
    
    def remove_websocket(self, websocket: WebSocket):
        if websocket in self.websocket_connections:
            self.websocket_connections.remove(websocket)


robot_controller = RobotController()


@app.get("/")
async def root():
    return {"status": "Robot Control API is running"}


@app.post("/api/orders")
async def create_order(request: CreateOrderRequest):
    import uuid
    order = Order(
        id=str(uuid.uuid4()),
        white_boxes=request.white_boxes,
        yellow_boxes=request.yellow_boxes
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
        "robot_status": robot_controller.status,
        "current_model": robot_controller.model_manager.current_color,
        "orders": list(robot_controller.orders.values())
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await robot_controller.add_websocket(websocket)
    try:
        while True:
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