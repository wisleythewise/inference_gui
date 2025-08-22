import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Package, Cpu, Activity, CheckCircle, AlertCircle, Loader2, Plus, X } from 'lucide-react';
import axios from 'axios';

const API_URL = 'http://localhost:8000';

function App() {
  const [robotStatus, setRobotStatus] = useState('idle');
  const [currentModel, setCurrentModel] = useState(null);
  const [orders, setOrders] = useState([]);
  const [ws, setWs] = useState(null);
  const [showCreateOrder, setShowCreateOrder] = useState(false);
  const [newOrder, setNewOrder] = useState({ white_boxes: 1, yellow_boxes: 1, black_boxes: 0 });
  const [selectedOrderId, setSelectedOrderId] = useState(null);
  const [isPickingInProgress, setIsPickingInProgress] = useState(false);

  useEffect(() => {
    const websocket = new WebSocket('ws://localhost:8000/ws');
    
    websocket.onopen = () => {
      console.log('WebSocket connected');
    };
    
    websocket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setRobotStatus(data.robot_status);
      setCurrentModel(data.current_model);
      setOrders(data.orders || []);
      setIsPickingInProgress(data.robot_status === 'picking' || data.robot_status === 'loading_model');
    };
    
    websocket.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
    
    setWs(websocket);
    
    fetchOrders();
    
    return () => {
      websocket.close();
    };
  }, []);

  const fetchOrders = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/orders`);
      setOrders(response.data);
    } catch (error) {
      console.error('Error fetching orders:', error);
    }
  };

  const handlePick = async (color) => {
    if (isPickingInProgress) return;
    
    try {
      await axios.post(`${API_URL}/api/pick`, {
        color,
        order_id: selectedOrderId
      });
    } catch (error) {
      console.error('Error picking box:', error);
    }
  };

  const createOrder = async () => {
    try {
      await axios.post(`${API_URL}/api/orders`, newOrder);
      setShowCreateOrder(false);
      setNewOrder({ white_boxes: 1, yellow_boxes: 1, black_boxes: 0 });
      fetchOrders();
    } catch (error) {
      console.error('Error creating order:', error);
    }
  };

  const deleteOrder = async (orderId) => {
    try {
      await axios.delete(`${API_URL}/api/orders/${orderId}`);
      if (selectedOrderId === orderId) {
        setSelectedOrderId(null);
      }
      fetchOrders();
    } catch (error) {
      console.error('Error deleting order:', error);
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'idle': return 'text-green-400';
      case 'loading_model': return 'text-yellow-400';
      case 'picking': return 'text-blue-400';
      case 'error': return 'text-red-400';
      default: return 'text-gray-400';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'idle': return <CheckCircle className="w-5 h-5" />;
      case 'loading_model': return <Loader2 className="w-5 h-5 animate-spin" />;
      case 'picking': return <Activity className="w-5 h-5 animate-pulse" />;
      case 'error': return <AlertCircle className="w-5 h-5" />;
      default: return <Activity className="w-5 h-5" />;
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-servo-black via-servo-gray to-servo-black">
      {/* Header */}
      <header className="border-b border-servo-light-gray/30 backdrop-blur-xl bg-servo-black/50">
        <div className="container mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <div className="w-10 h-10 bg-servo-accent rounded-lg flex items-center justify-center">
                <Package className="w-6 h-6 text-servo-black" />
              </div>
              <h1 className="text-2xl font-bold font-sans">S7 Robot Control</h1>
            </div>
            <div className="flex items-center space-x-4">
              <div className={`flex items-center space-x-2 ${getStatusColor(robotStatus)}`}>
                {getStatusIcon(robotStatus)}
                <span className="font-mono text-sm uppercase">{robotStatus}</span>
              </div>
              {currentModel && (
                <div className="flex items-center space-x-2 text-servo-accent">
                  <Cpu className="w-4 h-4" />
                  <span className="font-mono text-sm">{currentModel}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-6 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Control Panel */}
          <div className="lg:col-span-2">
            <motion.div 
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="glass-card p-8"
            >
              <h2 className="text-xl font-semibold mb-6 flex items-center space-x-2">
                <Activity className="w-5 h-5 text-servo-accent" />
                <span>Robot Controls</span>
              </h2>

              {selectedOrderId && (
                <div className="mb-6 p-4 bg-servo-accent/10 border border-servo-accent/30 rounded-lg">
                  <p className="text-sm text-servo-accent font-mono">
                    Active Order: {selectedOrderId.substring(0, 8)}...
                  </p>
                </div>
              )}

              <div className="grid grid-cols-3 gap-4">
                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => handlePick('white')}
                  disabled={isPickingInProgress}
                  className={`button-primary h-32 flex flex-col items-center justify-center space-y-3
                    ${isPickingInProgress 
                      ? 'bg-gray-800 cursor-not-allowed opacity-50' 
                      : 'bg-white text-servo-black hover:bg-gray-100'}`}
                >
                  <Package className="w-10 h-10" />
                  <span className="font-semibold">Pick White Box</span>
                  {currentModel === 'white' && robotStatus === 'loading_model' && (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  )}
                </motion.button>

                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => handlePick('yellow')}
                  disabled={isPickingInProgress}
                  className={`button-primary h-32 flex flex-col items-center justify-center space-y-3
                    ${isPickingInProgress 
                      ? 'bg-gray-800 cursor-not-allowed opacity-50' 
                      : 'bg-servo-yellow text-servo-black hover:bg-yellow-400'}`}
                >
                  <Package className="w-10 h-10" />
                  <span className="font-semibold">Pick Yellow Box</span>
                  {currentModel === 'yellow' && robotStatus === 'loading_model' && (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  )}
                </motion.button>

                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => handlePick('black')}
                  disabled={isPickingInProgress}
                  className={`button-primary h-32 flex flex-col items-center justify-center space-y-3
                    ${isPickingInProgress 
                      ? 'bg-gray-800 cursor-not-allowed opacity-50' 
                      : 'bg-gray-900 text-white hover:bg-gray-700'}`}
                >
                  <Package className="w-10 h-10" />
                  <span className="font-semibold">Pick Black Box</span>
                  {currentModel === 'black' && robotStatus === 'loading_model' && (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  )}
                </motion.button>
              </div>

              <div className="mt-8 p-4 bg-servo-light-gray/30 rounded-lg">
                <h3 className="text-sm font-mono text-gray-400 mb-2">System Info</h3>
                <div className="space-y-1 text-xs font-mono">
                  <p>GPU Memory: Optimized for single model</p>
                  <p>Model Switching: Automatic</p>
                  <p>Backend: LeRobot + HuggingFace</p>
                </div>
              </div>
            </motion.div>
          </div>

          {/* Orders Panel */}
          <div>
            <motion.div 
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className="glass-card p-6"
            >
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-semibold">Orders</h2>
                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={() => setShowCreateOrder(true)}
                  className="p-2 bg-servo-accent text-servo-black rounded-lg hover:bg-servo-accent/90"
                >
                  <Plus className="w-5 h-5" />
                </motion.button>
              </div>

              <div className="space-y-3 max-h-[600px] overflow-y-auto">
                <AnimatePresence>
                  {orders.length === 0 ? (
                    <p className="text-gray-500 text-center py-8">No orders yet</p>
                  ) : (
                    orders.map((order) => (
                      <motion.div
                        key={order.id}
                        initial={{ opacity: 0, x: -20 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0, x: 20 }}
                        onClick={() => setSelectedOrderId(order.id)}
                        className={`p-4 rounded-lg border cursor-pointer transition-all
                          ${selectedOrderId === order.id 
                            ? 'border-servo-accent bg-servo-accent/10' 
                            : 'border-servo-light-gray/50 hover:border-servo-light-gray'}`}
                      >
                        <div className="flex items-center justify-between mb-2">
                          <span className="font-mono text-xs text-gray-400">
                            {order.id.substring(0, 8)}...
                          </span>
                          <div className="flex items-center space-x-2">
                            <span className={`status-badge ${
                              order.status === 'completed' ? 'bg-green-500/20 text-green-400' :
                              order.status === 'in_progress' ? 'bg-blue-500/20 text-blue-400' :
                              'bg-gray-500/20 text-gray-400'
                            }`}>
                              {order.status}
                            </span>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                deleteOrder(order.id);
                              }}
                              className="p-1 hover:bg-red-500/20 rounded"
                            >
                              <X className="w-4 h-4 text-red-400" />
                            </button>
                          </div>
                        </div>
                        <div className="grid grid-cols-3 gap-2 mt-3">
                          <div className="flex items-center space-x-2">
                            <div className="w-4 h-4 bg-white rounded"></div>
                            <span className="text-xs">
                              {order.completed_white}/{order.white_boxes}
                            </span>
                          </div>
                          <div className="flex items-center space-x-2">
                            <div className="w-4 h-4 bg-servo-yellow rounded"></div>
                            <span className="text-xs">
                              {order.completed_yellow}/{order.yellow_boxes}
                            </span>
                          </div>
                          <div className="flex items-center space-x-2">
                            <div className="w-4 h-4 bg-gray-900 rounded"></div>
                            <span className="text-xs">
                              {(order.completed_black || 0)}/{order.black_boxes || 0}
                            </span>
                          </div>
                        </div>
                        {order.status === 'in_progress' && (
                          <div className="mt-3">
                            <div className="h-2 bg-servo-light-gray rounded-full overflow-hidden">
                              <motion.div
                                initial={{ width: 0 }}
                                animate={{ 
                                  width: `${(((order.completed_white || 0) + (order.completed_yellow || 0) + (order.completed_black || 0)) / 
                                    ((order.white_boxes || 0) + (order.yellow_boxes || 0) + (order.black_boxes || 0))) * 100}%` 
                                }}
                                className="h-full bg-servo-accent"
                              />
                            </div>
                          </div>
                        )}
                      </motion.div>
                    ))
                  )}
                </AnimatePresence>
              </div>
            </motion.div>
          </div>
        </div>
      </main>

      {/* Create Order Modal */}
      <AnimatePresence>
        {showCreateOrder && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center p-6 z-50"
            onClick={() => setShowCreateOrder(false)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
              className="glass-card p-6 max-w-md w-full"
            >
              <h3 className="text-xl font-semibold mb-4">Create New Order</h3>
              
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-2">White Boxes</label>
                  <input
                    type="number"
                    min="0"
                    max="10"
                    value={newOrder.white_boxes}
                    onChange={(e) => setNewOrder({ ...newOrder, white_boxes: parseInt(e.target.value) || 0 })}
                    className="w-full px-4 py-2 bg-servo-light-gray rounded-lg focus:outline-none focus:ring-2 focus:ring-servo-accent"
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium mb-2">Yellow Boxes</label>
                  <input
                    type="number"
                    min="0"
                    max="10"
                    value={newOrder.yellow_boxes}
                    onChange={(e) => setNewOrder({ ...newOrder, yellow_boxes: parseInt(e.target.value) || 0 })}
                    className="w-full px-4 py-2 bg-servo-light-gray rounded-lg focus:outline-none focus:ring-2 focus:ring-servo-accent"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">Black Boxes</label>
                  <input
                    type="number"
                    min="0"
                    max="10"
                    value={newOrder.black_boxes}
                    onChange={(e) => setNewOrder({ ...newOrder, black_boxes: parseInt(e.target.value) || 0 })}
                    className="w-full px-4 py-2 bg-servo-light-gray rounded-lg focus:outline-none focus:ring-2 focus:ring-servo-accent"
                  />
                </div>
              </div>

              <div className="flex space-x-3 mt-6">
                <button
                  onClick={createOrder}
                  className="flex-1 py-2 bg-servo-accent text-servo-black rounded-lg font-medium hover:bg-servo-accent/90"
                >
                  Create Order
                </button>
                <button
                  onClick={() => setShowCreateOrder(false)}
                  className="flex-1 py-2 bg-servo-light-gray rounded-lg font-medium hover:bg-servo-light-gray/80"
                >
                  Cancel
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default App;