const WebSocket = require('ws');

// Create WebSocket server on port 8080
const wss = new WebSocket.Server({ port: 8080 });

// Store connected clients
const clients = {
  webpages: new Set(),
  pcbs: new Set()
};

console.log('WebSocket server started on port 8080');

// Handle new connections
wss.on('connection', (ws) => {
  console.log('New client connected');
  
  // Handle messages from clients
  ws.on('message', (message) => {
    try {
      const data = JSON.parse(message);
      console.log('Received:', data);
      
      // Register client type
      if (data.type === 'register') {
        if (data.clientType === 'webpage') {
          clients.webpages.add(ws);
          ws.clientType = 'webpage';
          console.log('Webpage registered');
        } else if (data.clientType === 'pcb') {
          clients.pcbs.add(ws);
          ws.clientType = 'pcb';
          ws.deviceId = data.deviceId;
          console.log(`PCB registered: ${data.deviceId}`);
        }
      }
      
      // Handle commands from webpage to PCB
      if (data.type === 'command') {
        console.log(`Routing command to PCB ${data.targetPCB}`);
        clients.pcbs.forEach(pcb => {
          if (pcb.deviceId === data.targetPCB) {
            pcb.send(JSON.stringify({
              type: 'command',
              action: data.action,
              value: data.value
            }));
          }
        });
      }
      
      // Handle status updates from PCB to webpages
      if (data.type === 'status') {
        console.log('Broadcasting status to webpages');
        clients.webpages.forEach(webpage => {
          webpage.send(JSON.stringify({
            type: 'status',
            deviceId: ws.deviceId,
            data: data.data
          }));
        });
      }
      
    } catch (error) {
      console.error('Error processing message:', error);
    }
  });
  
  // Handle disconnection
  ws.on('close', () => {
    console.log('Client disconnected');
    clients.webpages.delete(ws);
    clients.pcbs.delete(ws);
  });
  
  // Handle errors
  ws.on('error', (error) => {
    console.error('WebSocket error:', error);
  });
});