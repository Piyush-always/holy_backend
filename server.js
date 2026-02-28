const WebSocket = require('ws');

const PORT = process.env.PORT || 8080;
const wss  = new WebSocket.Server({ port: PORT });

const clients = {
  webpages:    new Set(),
  pcbs:        new Map(),   // deviceId -> ws
  controllers: new Map(),   // deviceId -> ws
};

console.log(`WebSocket server started on port ${PORT}`);

wss.on('connection', (ws) => {
  ws.isAlive = true;
  ws.on('pong', () => { ws.isAlive = true; });

  ws.on('message', (message) => {
    try {
      const data = JSON.parse(message);

      if (data.type === 'ping') return;

      // ── REGISTER ──────────────────────────────────────────────
      if (data.type === 'register') {
        if (data.clientType === 'webpage') {
          clients.webpages.add(ws);
          ws.clientType = 'webpage';
          console.log('Webpage registered');
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
        return;
      }

      // ── COMMAND ───────────────────────────────────────────────
      if (data.type === 'command') {
        const from = ws.deviceId || ws.clientType || 'unknown';

        // Support single target {t} or multiple {targets:[]}
        let targetList = [];
        if (Array.isArray(data.targets) && data.targets.length > 0) {
          targetList = data.targets;
        } else if (data.t) {
          targetList = [data.t];
        } else if (data.targetPCB) {
          targetList = [data.targetPCB];
        }

        console.log(`Command [${from}] → [${targetList.join(', ')}] d:${data.d} s:${data.s}`);

        targetList.forEach(target => {
          const pcb = clients.pcbs.get(target);
          if (pcb && pcb.readyState === WebSocket.OPEN) {
            pcb.send(JSON.stringify({ type: 'command', d: data.d, s: data.s, from }));
            console.log(`  ✓ Delivered to [${target}]`);
          } else {
            console.log(`  ✗ [${target}] not connected`);
          }
        });

        notifyWebpages({ type: 'command', d: data.d, s: data.s, targets: targetList, from });
        return;
      }

      if (data.type === 'status') {
        notifyWebpages({ type: 'status', deviceId: ws.deviceId, message: data.message || '' });
      }

    } catch (err) {
      console.error('Message error:', err);
    }
  });

  ws.on('close', () => {
    const id = ws.deviceId;
    clients.webpages.delete(ws);
    if (ws.clientType === 'pcb')        clients.pcbs.delete(id);
    if (ws.clientType === 'controller') clients.controllers.delete(id);
    console.log(`Disconnected: [${ws.clientType}] ${id || ''}`);
    if (id) notifyWebpages({ type: 'device_disconnected', deviceId: id });
  });

  ws.on('error', (err) => console.error('WS error:', err));
});

// Server-side heartbeat — kills dead connections
const heartbeat = setInterval(() => {
  wss.clients.forEach(ws => {
    if (!ws.isAlive) { console.log('Dead connection terminated'); return ws.terminate(); }
    ws.isAlive = false;
    ws.ping();
  });
}, 30000);

wss.on('close', () => clearInterval(heartbeat));

function notifyWebpages(payload) {
  const msg = JSON.stringify(payload);
  clients.webpages.forEach(wp => {
    if (wp.readyState === WebSocket.OPEN) wp.send(msg);
  });
}
