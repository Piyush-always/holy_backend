const WebSocket = require('ws');

const PORT = process.env.PORT || 8080;
const wss = new WebSocket.Server({ port: PORT });

const clients = {
  webpages:    new Set(),
  pcbs:        new Map(),   // deviceId -> ws
  controllers: new Map(),   // deviceId -> ws
};

console.log(`WebSocket server started on port ${PORT}`);

wss.on('connection', (ws) => {
  console.log('New client connected');

  ws.on('message', (message) => {
    try {
      const data = JSON.parse(message);
      console.log('Received:', data);

      // ── REGISTER ──────────────────────────────────────────────
      if (data.type === 'register') {

        if (data.clientType === 'webpage') {
          clients.webpages.add(ws);
          ws.clientType = 'webpage';
          console.log('Webpage registered');
          // Tell webpage which devices are already online
          clients.pcbs.forEach((_, id) =>
            ws.send(JSON.stringify({ type: 'device_connected', deviceId: id }))
          );
          clients.controllers.forEach((_, id) =>
            ws.send(JSON.stringify({ type: 'device_connected', deviceId: id }))
          );

        } else if (data.clientType === 'pcb') {
          ws.clientType = 'pcb';
          ws.deviceId = data.deviceId;
          clients.pcbs.set(data.deviceId, ws);
          console.log(`PCB registered: ${data.deviceId}`);
          notifyWebpages({ type: 'device_connected', deviceId: data.deviceId });

        } else if (data.clientType === 'controller') {
          ws.clientType = 'controller';
          ws.deviceId = data.deviceId;
          clients.controllers.set(data.deviceId, ws);
          console.log(`Controller registered: ${data.deviceId}`);
          notifyWebpages({ type: 'device_connected', deviceId: data.deviceId });
        }
      }

      // ── COMMAND ───────────────────────────────────────────────
      // Short format: { type, d, s, t }
      if (data.type === 'command') {
        const target = data.t || data.targetPCB;
        console.log(`Command [${ws.clientType}/${ws.deviceId}] → ${target} | d:${data.d} s:${data.s}`);

        // Forward to target PCB
        const targetPcb = clients.pcbs.get(target);
        if (targetPcb && targetPcb.readyState === WebSocket.OPEN) {
          targetPcb.send(JSON.stringify({
            type: 'command',
            d:    data.d,
            s:    data.s,
            from: ws.deviceId || ws.clientType,
          }));
          console.log(`  ✓ Delivered to [${target}]`);
        } else {
          console.log(`  ✗ [${target}] not connected`);
        }

        // Mirror to webpages for live log
        notifyWebpages({
          type: 'command',
          d:    data.d,
          s:    data.s,
          t:    target,
          from: ws.deviceId || ws.clientType,
        });
      }

      // ── STATUS from PCB ───────────────────────────────────────
      if (data.type === 'status') {
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

function notifyWebpages(payload) {
  const msg = JSON.stringify(payload);
  clients.webpages.forEach(wp => {
    if (wp.readyState === WebSocket.OPEN) wp.send(msg);
  });
}
