const WebSocket = require('ws');

const wss = new WebSocket.Server({ port: 8080 });

// Store connected clients
const clients = {
  webpages:     new Set(),
  pcbs:         new Map(),   // deviceId -> ws
  controllers:  new Map(),   // deviceId -> ws
};

console.log('WebSocket server started on port 8080');

wss.on('connection', (ws) => {
  console.log('New client connected');

  ws.on('message', (message) => {
    try {
      const data = JSON.parse(message);
      console.log('Received:', data);

      // ── REGISTER ────────────────────────────────────────────────
      if (data.type === 'register') {

        if (data.clientType === 'webpage') {
          clients.webpages.add(ws);
          ws.clientType = 'webpage';
          console.log('Webpage registered');

          // Tell webpage about all currently connected devices
          clients.pcbs.forEach((_, id) =>
            ws.send(JSON.stringify({ type: 'device_connected', deviceId: id }))
          );
          clients.controllers.forEach((_, id) =>
            ws.send(JSON.stringify({ type: 'device_connected', deviceId: id }))
          );

        } else if (data.clientType === 'pcb') {
          ws.clientType = 'pcb';
          ws.deviceId   = data.deviceId;
          clients.pcbs.set(data.deviceId, ws);
          console.log(`PCB registered: ${data.deviceId}`);
          notifyWebpages({ type: 'device_connected', deviceId: data.deviceId });

        } else if (data.clientType === 'controller') {
          ws.clientType = 'controller';
          ws.deviceId   = data.deviceId;
          clients.controllers.set(data.deviceId, ws);
          console.log(`Controller registered: ${data.deviceId}`);
          notifyWebpages({ type: 'device_connected', deviceId: data.deviceId });
        }
      }

      // ── COMMAND ─────────────────────────────────────────────────
      // Accepts both short format {d, s, t} and old format {action, targetPCB}
      if (data.type === 'command') {
        const target = data.t || data.targetPCB;  // support both formats
        console.log(`Command from [${ws.clientType}] → target: ${target} | d:${data.d} s:${data.s}`);

        // Forward to target PCB
        const targetPcb = clients.pcbs.get(target);
        if (targetPcb && targetPcb.readyState === WebSocket.OPEN) {
          targetPcb.send(JSON.stringify({
            type: 'command',
            d:    data.d,
            s:    data.s,
            from: ws.deviceId || ws.clientType,
          }));
          console.log(`  ✓ Delivered to PCB [${target}]`);
        } else {
          console.log(`  ✗ PCB [${target}] not connected`);
        }

        // Also mirror to all webpages so they see the live log
        notifyWebpages({
          type: 'command',
          d:    data.d,
          s:    data.s,
          t:    target,
          from: ws.deviceId || ws.clientType,
        });
      }

      // ── STATUS from PCB ─────────────────────────────────────────
      if (data.type === 'status') {
        console.log(`Status from PCB [${ws.deviceId}]`);
        notifyWebpages({
          type:     'status',
          deviceId: ws.deviceId,
          message:  data.message || '',
        });
      }

    } catch (error) {
      console.error('Error processing message:', error);
    }
  });

  ws.on('close', () => {
    const id = ws.deviceId;
    console.log(`Disconnected: [${ws.clientType}] ${id || ''}`);

    clients.webpages.delete(ws);
    if (ws.clientType === 'pcb')        clients.pcbs.delete(id);
    if (ws.clientType === 'controller') clients.controllers.delete(id);

    if (id) notifyWebpages({ type: 'device_disconnected', deviceId: id });
  });

  ws.on('error', (err) => console.error('WS error:', err));
});

// ── Helper ────────────────────────────────────────────────────────
function notifyWebpages(payload) {
  const msg = JSON.stringify(payload);
  clients.webpages.forEach(wp => {
    if (wp.readyState === WebSocket.OPEN) wp.send(msg);
  });
}
