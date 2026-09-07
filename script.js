(function () {
    "use strict";

    /* ---------- Konfigurasi dasar ---------- */
    const ROWS = 16,
        COLS = 22,
        CELL = 30;
    const GRASS = 0,
        TREE = 1,
        HOUSE = 2,
        RIVER = 3;
    const RIVER_COST = 4;
    const canvas = document.getElementById('board');
    const ctx = canvas.getContext('2d');

    let grid = [];
    let passableCells = []; // {r,c} cache untuk sampling cepat
    let player = {
        r: 1,
        c: 1
    };
    let npc = {
        r: 1,
        c: 1
    };
    let npcPath = null;
    let lastSearchResult = null;
    let npcTimer = null;

    const state = {
        mode: 'single', // 'single' | 'multi'
        algo: 'astar',
        heuristic: 'octile',
        diagonal: true,
        showExplored: false,
        speedMs: 220
    };

    /* ---------- Multiplayer: konstanta & state ---------- */
    const MP_CORNERS = [{
        r: 1,
        c: 1
    }, {
        r: 1,
        c: COLS - 2
    }, {
        r: ROWS - 2,
        c: 1
    }, {
        r: ROWS - 2,
        c: COLS - 2
    }];
    const MP_COLORS = ['#e3ad4c', '#5bc8d9', '#d962c0', '#7ed957'];
    const MP_NAMES = ['P1', 'P2', 'P3', 'P4'];
    const MP_DEFAULT_CONTROLS = [{
        up: 'w',
        down: 's',
        left: 'a',
        right: 'd'
    }, {
        up: 'arrowup',
        down: 'arrowdown',
        left: 'arrowleft',
        right: 'arrowright'
    }, {
        up: 'i',
        down: 'k',
        left: 'j',
        right: 'l'
    }, {
        up: '8',
        down: '5',
        left: '4',
        right: '6'
    }];

    let multi = {
        numPlayers: 2,
        players: [],
        ghosts: [],
        coins: [],
        active: false,
        over: false,
        tickTimer: null,
        listeningFor: null // {idx, dir} saat menunggu tombol baru
    };

    /* ---------- Util grid ---------- */
    function keyOf(r, c) {
        return r * COLS + c;
    }

    function inBounds(r, c) {
        return r >= 0 && r < ROWS && c >= 0 && c < COLS;
    }

    function isPassable(r, c) {
        return inBounds(r, c) && grid[r][c] !== TREE && grid[r][c] !== HOUSE;
    }

    function terrainCost(r, c) {
        return grid[r][c] === RIVER ? RIVER_COST : 1;
    }

    function neighborsOf(r, c, diagonal) {
        const orth = [
            [1, 0],
            [-1, 0],
            [0, 1],
            [0, -1]
        ];
        const diag = [
            [1, 1],
            [1, -1],
            [-1, 1],
            [-1, -1]
        ];
        const dirs = diagonal ? orth.concat(diag) : orth;
        const out = [];
        for (const [dr, dc] of dirs) {
            const nr = r + dr,
                nc = c + dc;
            if (!isPassable(nr, nc)) continue;
            if (dr !== 0 && dc !== 0) {
                // cegah "memotong sudut" lewat celah antar dua penghalang
                if (!isPassable(r + dr, c) || !isPassable(r, c + dc)) continue;
            }
            out.push([nr, nc]);
        }
        return out;
    }

    function moveCost(r, c, nr, nc) {
        const base = terrainCost(nr, nc);
        const diagonal = (r !== nr && c !== nc);
        return diagonal ? base * Math.SQRT2 : base;
    }

    /* ---------- Heuristik ---------- */
    const HEURISTICS = {
        manhattan: (a, b) => Math.abs(a.r - b.r) + Math.abs(a.c - b.c),
        euclidean: (a, b) => Math.hypot(a.r - b.r, a.c - b.c),
        chebyshev: (a, b) => Math.max(Math.abs(a.r - b.r), Math.abs(a.c - b.c)),
        octile: (a, b) => {
            const dx = Math.abs(a.r - b.r),
                dy = Math.abs(a.c - b.c);
            return (dx + dy) + (Math.SQRT2 - 2) * Math.min(dx, dy);
        },
        zero: () => 0
    };

    /* ---------- Pencarian: UCS = A* dengan heuristik nol ---------- */
    function search(start, goal, diagonal, heuristicFn) {
        const t0 = performance.now();
        const gScore = new Map();
        const cameFrom = new Map();
        const startKey = keyOf(start.r, start.c);
        gScore.set(startKey, 0);
        const open = [{
            r: start.r,
            c: start.c,
            g: 0,
            f: heuristicFn(start, goal)
        }];
        const closed = new Set();
        const visited = [];
        let nodesExpanded = 0;

        while (open.length) {
            let minIdx = 0;
            for (let i = 1; i < open.length; i++) {
                if (open[i].f < open[minIdx].f) minIdx = i;
            }
            const current = open.splice(minIdx, 1)[0];
            const ck = keyOf(current.r, current.c);
            if (closed.has(ck)) continue;
            closed.add(ck);
            nodesExpanded++;
            visited.push({
                r: current.r,
                c: current.c
            });

            if (current.r === goal.r && current.c === goal.c) {
                const path = [{
                    r: current.r,
                    c: current.c
                }];
                let k = ck;
                while (cameFrom.has(k)) {
                    k = cameFrom.get(k);
                    path.push({
                        r: Math.floor(k / COLS),
                        c: k % COLS
                    });
                }
                path.reverse();
                return {
                    path,
                    cost: current.g,
                    nodesExpanded,
                    timeMs: performance.now() - t0,
                    visited
                };
            }

            for (const [nr, nc] of neighborsOf(current.r, current.c, diagonal)) {
                const nk = keyOf(nr, nc);
                if (closed.has(nk)) continue;
                const g2 = current.g + moveCost(current.r, current.c, nr, nc);
                if (!gScore.has(nk) || g2 < gScore.get(nk) - 1e-9) {
                    gScore.set(nk, g2);
                    cameFrom.set(nk, ck);
                    open.push({
                        r: nr,
                        c: nc,
                        g: g2,
                        f: g2 + heuristicFn({
                            r: nr,
                            c: nc
                        }, goal)
                    });
                }
            }
        }
        return {
            path: null,
            cost: Infinity,
            nodesExpanded,
            timeMs: performance.now() - t0,
            visited
        };
    }

    /* ---------- Pembuatan peta ---------- */
    function blankGrid() {
        const g = [];
        for (let r = 0; r < ROWS; r++) {
            g.push(new Array(COLS).fill(GRASS));
        }
        return g;
    }

    function placeHouses(g) {
        const houses = 4;
        let tries = 0;
        let placed = 0;
        while (placed < houses && tries < 200) {
            tries++;
            const w = 2 + (Math.random() < 0.5 ? 0 : 1);
            const h = 2;
            const r0 = 2 + Math.floor(Math.random() * (ROWS - h - 4));
            const c0 = 2 + Math.floor(Math.random() * (COLS - w - 4));
            let clear = true;
            for (let r = r0 - 1; r <= r0 + h; r++) {
                for (let c = c0 - 1; c <= c0 + w; c++) {
                    if (!inBounds(r, c) || g[r][c] !== GRASS) {
                        clear = false;
                        break;
                    }
                }
                if (!clear) break;
            }
            if (!clear) continue;
            for (let r = r0; r < r0 + h; r++) {
                for (let c = c0; c < c0 + w; c++) {
                    g[r][c] = HOUSE;
                }
            }
            placed++;
        }
    }

    function placeTrees(g) {
        const count = 40;
        let placed = 0,
            tries = 0;
        while (placed < count && tries < 400) {
            tries++;
            const r = Math.floor(Math.random() * ROWS);
            const c = Math.floor(Math.random() * COLS);
            if (g[r][c] !== GRASS) continue;
            g[r][c] = TREE;
            placed++;
        }
    }

    function placeRiver(g) {
        let c = 5 + Math.floor(Math.random() * (COLS - 10));
        let drift = 0;
        for (let r = 0; r < ROWS; r++) {
            drift += (Math.random() < 0.5 ? -1 : 1);
            drift = Math.max(-1, Math.min(1, drift));
            c = Math.max(2, Math.min(COLS - 3, c + drift));
            const width = Math.random() < 0.3 ? 2 : 1;
            for (let w = 0; w < width; w++) {
                const cc = c + w;
                if (inBounds(r, cc) && g[r][cc] !== HOUSE) g[r][cc] = RIVER;
            }
        }
    }

    function countPassable(g) {
        let n = 0;
        for (let r = 0; r < ROWS; r++)
            for (let c = 0; c < COLS; c++)
                if (g[r][c] !== TREE && g[r][c] !== HOUSE) n++;
        return n;
    }

    function largestComponentSize(g) {
        const seen = new Array(ROWS * COLS).fill(false);
        let best = 0;
        for (let r = 0; r < ROWS; r++) {
            for (let c = 0; c < COLS; c++) {
                if (g[r][c] === TREE || g[r][c] === HOUSE) continue;
                const k = keyOf(r, c);
                if (seen[k]) continue;
                // BFS abaikan biaya, hanya cek keterhubungan (gerak 4 arah cukup untuk syarat konektivitas dasar)
                let size = 0;
                const stack = [
                    [r, c]
                ];
                seen[k] = true;
                while (stack.length) {
                    const [cr, cc] = stack.pop();
                    size++;
                    for (const [dr, dc] of [
                            [1, 0],
                            [-1, 0],
                            [0, 1],
                            [0, -1]
                        ]) {
                        const nr = cr + dr,
                            nc = cc + dc;
                        if (!inBounds(nr, nc)) continue;
                        if (g[nr][nc] === TREE || g[nr][nc] === HOUSE) continue;
                        const nk = keyOf(nr, nc);
                        if (seen[nk]) continue;
                        seen[nk] = true;
                        stack.push([nr, nc]);
                    }
                }
                best = Math.max(best, size);
            }
        }
        return best;
    }

    // Posisi awal pemain selalu tetap di sudut kiri-atas area bermain (bukan acak).
    // Jika sel itu terhalang di peta yang baru dibuat, ambil sel bisa-dilewati terdekat.
    const FIXED_PLAYER_SPAWN = {
        r: 1,
        c: 1
    };

    function nearestPassableCell(tr, tc) {
        let best = null,
            bestD = Infinity;
        for (const p of passableCells) {
            const d = Math.hypot(p.r - tr, p.c - tc);
            if (d < bestD) {
                bestD = d;
                best = p;
            }
        }
        return best;
    }

    function farthestPassableCell(from) {
        let best = null,
            bestD = -1;
        for (const p of passableCells) {
            const d = Math.max(Math.abs(p.r - from.r), Math.abs(p.c - from.c));
            if (d > bestD) {
                bestD = d;
                best = p;
            }
        }
        return best;
    }

    function placeEntitiesFixed() {
        const spawn = nearestPassableCell(FIXED_PLAYER_SPAWN.r, FIXED_PLAYER_SPAWN.c);
        player = {
            r: spawn.r,
            c: spawn.c
        };
        const far = farthestPassableCell(player);
        npc = {
            r: far.r,
            c: far.c
        };
    }

    function buildGrid() {
        let attempts = 0;
        let g;
        do {
            g = blankGrid();
            placeRiver(g);
            placeHouses(g);
            placeTrees(g);
            attempts++;
        } while (largestComponentSize(g) < countPassable(g) * 0.85 && attempts < 20);
        return g;
    }

    function computePassable(g) {
        const cells = [];
        for (let r = 0; r < ROWS; r++)
            for (let c = 0; c < COLS; c++)
                if (g[r][c] !== TREE && g[r][c] !== HOUSE) cells.push({
                    r,
                    c
                });
        return cells;
    }

    function generateMap() {
        grid = buildGrid();
        passableCells = computePassable(grid);
        placeEntitiesFixed();
        npcPath = null;
        lastSearchResult = null;
    }

    function respawnPositions() {
        placeEntitiesFixed();
    }

    /* ---------- Multiplayer: peta, koin, pemain, hantu ---------- */
    function setupCoins(spawnCells) {
        const coins = [];
        for (let r = 0; r < ROWS; r += 2) {
            for (let c = 0; c < COLS; c += 2) {
                if (!isPassable(r, c)) continue;
                const nearSpawn = spawnCells.some(s => Math.abs(s.r - r) <= 1 && Math.abs(s.c - c) <= 1);
                if (nearSpawn) continue;
                coins.push({
                    r,
                    c
                });
            }
        }
        return coins;
    }

    function generateMultiplayerMap() {
        grid = buildGrid();
        passableCells = computePassable(grid);

        const n = multi.numPlayers;
        const spawnPts = MP_CORNERS.slice(0, n).map(p => nearestPassableCell(p.r, p.c));
        const prevControls = multi.players.map(p => p.controls);
        multi.players = spawnPts.map((sp, i) => ({
            id: i,
            name: MP_NAMES[i],
            color: MP_COLORS[i],
            r: sp.r,
            c: sp.c,
            spawn: {
                r: sp.r,
                c: sp.c
            },
            lives: 3,
            score: 0,
            alive: true,
            invulnUntil: 0,
            controls: prevControls[i] ? Object.assign({}, prevControls[i]) : Object.assign({}, MP_DEFAULT_CONTROLS[i])
        }));

        const center = nearestPassableCell(Math.floor(ROWS / 2), Math.floor(COLS / 2));
        const ghostCount = n >= 3 ? 2 : 1;
        multi.ghosts = [];
        for (let i = 0; i < ghostCount; i++) {
            const gp = i === 0 ? center : farthestPassableCell(center);
            multi.ghosts.push({
                r: gp.r,
                c: gp.c
            });
        }

        multi.coins = setupCoins(spawnPts);
        multi.active = false;
        multi.over = false;
        npcPath = null;
        lastSearchResult = null;
    }

    /* ---------- Render ---------- */
    function drawTile(r, c) {
        const x = c * CELL,
            y = r * CELL;
        const type = grid[r][c];
        if (type === GRASS) {
            ctx.fillStyle = (r + c) % 2 === 0 ? '#3c6b35' : '#356030';
            ctx.fillRect(x, y, CELL, CELL);
        } else if (type === RIVER) {
            ctx.fillStyle = '#2f6f8f';
            ctx.fillRect(x, y, CELL, CELL);
            ctx.strokeStyle = 'rgba(127,199,221,0.55)';
            ctx.lineWidth = 1.4;
            ctx.beginPath();
            const wave = ((r * 7 + c * 3) % 4) - 1;
            ctx.moveTo(x + 3, y + CELL / 2 + wave);
            ctx.bezierCurveTo(x + CELL * 0.35, y + CELL / 2 - 4 + wave, x + CELL * 0.65, y + CELL / 2 + 4 + wave, x + CELL - 3, y + CELL / 2 + wave);
            ctx.stroke();
        } else if (type === TREE) {
            ctx.fillStyle = '#345c2e';
            ctx.fillRect(x, y, CELL, CELL);
            ctx.fillStyle = '#4a3222';
            ctx.fillRect(x + CELL / 2 - 2, y + CELL * 0.55, 4, CELL * 0.4);
            ctx.fillStyle = '#20361c';
            ctx.beginPath();
            ctx.arc(x + CELL / 2, y + CELL * 0.42, CELL * 0.34, 0, Math.PI * 2);
            ctx.fill();
            ctx.fillStyle = '#2f4d28';
            ctx.beginPath();
            ctx.arc(x + CELL * 0.38, y + CELL * 0.34, CELL * 0.2, 0, Math.PI * 2);
            ctx.fill();
        } else if (type === HOUSE) {
            ctx.fillStyle = '#d8c9a3';
            ctx.fillRect(x + 2, y + 2, CELL - 4, CELL - 4);
            const topIsHouse = inBounds(r - 1, c) && grid[r - 1][c] === HOUSE;
            if (!topIsHouse) {
                ctx.fillStyle = '#8a3b2c';
                ctx.beginPath();
                ctx.moveTo(x, y + CELL * 0.42);
                ctx.lineTo(x + CELL / 2, y - 2);
                ctx.lineTo(x + CELL, y + CELL * 0.42);
                ctx.closePath();
                ctx.fill();
            } else {
                ctx.fillStyle = 'rgba(138,59,44,0.35)';
                ctx.fillRect(x + 2, y + 2, CELL - 4, 5);
            }
            ctx.fillStyle = '#6e2e21';
            ctx.fillRect(x + CELL / 2 - 3, y + CELL - 11, 6, 9);
        }
    }

    function drawExploredOverlay() {
        if (!state.showExplored || !lastSearchResult || !lastSearchResult.visited) return;
        const total = lastSearchResult.visited.length;
        lastSearchResult.visited.forEach((n, i) => {
            const alpha = 0.08 + 0.30 * (i / Math.max(1, total));
            ctx.fillStyle = `rgba(95,160,220,${alpha.toFixed(3)})`;
            ctx.fillRect(n.c * CELL + 2, n.r * CELL + 2, CELL - 4, CELL - 4);
        });
    }

    function drawPathOverlay() {
        if (!npcPath || npcPath.length < 2) return;
        const total = npcPath.length;
        npcPath.forEach((n, i) => {
            const alpha = 0.14 + 0.22 * (i / total);
            ctx.fillStyle = `rgba(227,173,76,${alpha.toFixed(3)})`;
            ctx.fillRect(n.c * CELL + 7, n.r * CELL + 7, CELL - 14, CELL - 14);
        });
    }

    function drawEntities() {
        // player
        const px = player.c * CELL + CELL / 2,
            py = player.r * CELL + CELL / 2;
        const grad = ctx.createRadialGradient(px, py, 2, px, py, CELL * 0.65);
        grad.addColorStop(0, 'rgba(227,173,76,0.55)');
        grad.addColorStop(1, 'rgba(227,173,76,0)');
        ctx.fillStyle = grad;
        ctx.fillRect(px - CELL * 0.65, py - CELL * 0.65, CELL * 1.3, CELL * 1.3);
        ctx.fillStyle = '#e3ad4c';
        ctx.beginPath();
        ctx.arc(px, py, CELL * 0.32, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = '#7a5417';
        ctx.lineWidth = 1.6;
        ctx.stroke();

        // npc (segitiga)
        const nx = npc.c * CELL + CELL / 2,
            ny = npc.r * CELL + CELL / 2;
        let angle = -Math.PI / 2;
        if (npcPath && npcPath.length > 1) {
            angle = Math.atan2(npcPath[1].r - npc.r, npcPath[1].c - npc.c);
        }
        ctx.save();
        ctx.translate(nx, ny);
        ctx.rotate(angle + Math.PI / 2);
        ctx.fillStyle = '#e0533d';
        ctx.beginPath();
        ctx.moveTo(0, -CELL * 0.34);
        ctx.lineTo(CELL * 0.26, CELL * 0.28);
        ctx.lineTo(-CELL * 0.26, CELL * 0.28);
        ctx.closePath();
        ctx.fill();
        ctx.strokeStyle = '#7d2113';
        ctx.lineWidth = 1.4;
        ctx.stroke();
        ctx.restore();
    }

    function drawCoins() {
        multi.coins.forEach(k => {
            const x = k.c * CELL + CELL / 2,
                y = k.r * CELL + CELL / 2;
            ctx.fillStyle = '#f4d35e';
            ctx.beginPath();
            ctx.arc(x, y, 4, 0, Math.PI * 2);
            ctx.fill();
            ctx.strokeStyle = 'rgba(0,0,0,0.25)';
            ctx.lineWidth = 1;
            ctx.stroke();
        });
    }

    function drawMultiEntities() {
        const now = performance.now();
        multi.players.forEach(p => {
            if (!p.alive) return;
            const blinking = p.invulnUntil && now < p.invulnUntil && Math.floor(now / 150) % 2 === 0;
            if (blinking) return;
            const px = p.c * CELL + CELL / 2,
                py = p.r * CELL + CELL / 2;
            ctx.fillStyle = p.color;
            ctx.beginPath();
            ctx.arc(px, py, CELL * 0.32, 0, Math.PI * 2);
            ctx.fill();
            ctx.strokeStyle = 'rgba(0,0,0,0.35)';
            ctx.lineWidth = 1.6;
            ctx.stroke();
            ctx.fillStyle = '#1a1a1a';
            ctx.font = 'bold 12px sans-serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(String(p.id + 1), px, py + 1);
        });
        multi.ghosts.forEach(g => {
            const nx = g.c * CELL + CELL / 2,
                ny = g.r * CELL + CELL / 2;
            ctx.fillStyle = '#e0533d';
            ctx.beginPath();
            ctx.arc(nx, ny, CELL * 0.3, 0, Math.PI * 2);
            ctx.fill();
            ctx.strokeStyle = '#7d2113';
            ctx.lineWidth = 1.4;
            ctx.stroke();
            ctx.fillStyle = '#fff';
            ctx.beginPath();
            ctx.arc(nx - 4, ny - 3, 2.4, 0, Math.PI * 2);
            ctx.fill();
            ctx.beginPath();
            ctx.arc(nx + 4, ny - 3, 2.4, 0, Math.PI * 2);
            ctx.fill();
            ctx.fillStyle = '#222';
            ctx.beginPath();
            ctx.arc(nx - 4, ny - 3, 1.1, 0, Math.PI * 2);
            ctx.fill();
            ctx.beginPath();
            ctx.arc(nx + 4, ny - 3, 1.1, 0, Math.PI * 2);
            ctx.fill();
        });
    }

    function draw() {
        for (let r = 0; r < ROWS; r++)
            for (let c = 0; c < COLS; c++) drawTile(r, c);
        if (state.mode === 'multi') {
            drawCoins();
            drawMultiEntities();
        } else {
            drawExploredOverlay();
            drawPathOverlay();
            drawEntities();
        }
    }

    /* ---------- Logika NPC & pemain ---------- */
    function currentHeuristicFn() {
        return state.algo === 'ucs' ? HEURISTICS.zero : HEURISTICS[state.heuristic];
    }

    function updateStatsPanel(res) {
        document.getElementById('statAlgo').textContent = state.algo === 'ucs' ? 'UCS' : ('A* · ' + state.heuristic);
        document.getElementById('statNodes').textContent = res.nodesExpanded;
        document.getElementById('statLen').textContent = res.path ? res.path.length : '—';
        document.getElementById('statCost').textContent = res.path ? res.cost.toFixed(2) : 'tidak ada jalur';
        document.getElementById('statTime').textContent = res.timeMs.toFixed(2) + ' ms';
    }

    function recomputeNpcPath() {
        const res = search(npc, player, state.diagonal, currentHeuristicFn());
        lastSearchResult = res;
        npcPath = res.path || [{
            r: npc.r,
            c: npc.c
        }];
        updateStatsPanel(res);
    }

    function showToast(msg) {
        const el = document.getElementById('toast');
        el.textContent = msg;
        el.classList.remove('hidden');
        setTimeout(() => el.classList.add('hidden'), 900);
    }

    function onCapture() {
        showToast('NPC menangkap pemain! Posisi direset.');
        setTimeout(() => {
            const spawn = nearestPassableCell(FIXED_PLAYER_SPAWN.r, FIXED_PLAYER_SPAWN.c);
            player = {
                r: spawn.r,
                c: spawn.c
            };
            const far = farthestPassableCell(player);
            npc = {
                r: far.r,
                c: far.c
            };
            recomputeNpcPath();
            draw();
        }, 500);
    }

    function stopSingleLoop() {
        clearTimeout(npcTimer);
    }

    function startSingleLoop() {
        clearTimeout(npcTimer);
        npcTimer = setTimeout(npcTick, state.speedMs);
    }

    function npcTick() {
        if (state.mode !== 'single') return;
        recomputeNpcPath();
        if (npcPath.length > 1) {
            npc = {
                r: npcPath[1].r,
                c: npcPath[1].c
            };
        }
        if (npc.r === player.r && npc.c === player.c) {
            onCapture();
        }
        draw();
        npcTimer = setTimeout(npcTick, state.speedMs);
    }

    function tryMovePlayer(r, c) {
        if (!isPassable(r, c)) return;
        player = {
            r,
            c
        };
        recomputeNpcPath();
        draw();
    }

    /* ---------- Event handling ---------- */
    canvas.addEventListener('click', (e) => {
        if (state.mode !== 'single') return;
        const rect = canvas.getBoundingClientRect();
        const scaleX = canvas.width / rect.width,
            scaleY = canvas.height / rect.height;
        const x = (e.clientX - rect.left) * scaleX,
            y = (e.clientY - rect.top) * scaleY;
        const c = Math.floor(x / CELL),
            r = Math.floor(y / CELL);
        if (inBounds(r, c)) tryMovePlayer(r, c);
    });

    function normKey(k) {
        return (k || '').toLowerCase();
    }

    function keyLabel(k) {
        const map = {
            arrowup: '↑',
            arrowdown: '↓',
            arrowleft: '←',
            arrowright: '→',
            ' ': 'Space'
        };
        if (map[k]) return map[k];
        return k.length === 1 ? k.toUpperCase() : k;
    }

    function handleMultiplayerKey(e) {
        if (!multi.active || multi.over) return;
        const k = normKey(e.key);
        let moved = false;
        multi.players.forEach((p) => {
            if (!p.alive) return;
            const c = p.controls;
            let dr = 0,
                dc = 0;
            if (k === c.up) dr = -1;
            else if (k === c.down) dr = 1;
            else if (k === c.left) dc = -1;
            else if (k === c.right) dc = 1;
            else return;
            moved = true;
            movePlayerMulti(p, dr, dc);
        });
        if (moved) {
            e.preventDefault();
            draw();
        }
    }

    window.addEventListener('keydown', (e) => {
        // Menangkap tombol baru saat mengatur ulang kontrol pemain
        if (multi.listeningFor) {
            e.preventDefault();
            const {
                idx,
                dir
            } = multi.listeningFor;
            const newKey = normKey(e.key);
            const conflict = multi.players.some((p, i) => i !== idx && Object.values(p.controls).includes(newKey));
            if (conflict) {
                showToast('Tombol itu sudah dipakai pemain lain.');
                return;
            }
            multi.players[idx].controls[dir] = newKey;
            multi.listeningFor = null;
            renderPlayerControlsUI();
            return;
        }

        const tag = e.target && e.target.tagName;
        if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;

        if (state.mode === 'multi') {
            handleMultiplayerKey(e);
            return;
        }

        const map = {
            ArrowUp: [-1, 0],
            ArrowDown: [1, 0],
            ArrowLeft: [0, -1],
            ArrowRight: [0, 1],
            w: [-1, 0],
            s: [1, 0],
            a: [0, -1],
            d: [0, 1],
            W: [-1, 0],
            S: [1, 0],
            A: [0, -1],
            D: [0, 1]
        };
        if (!map[e.key]) return;
        e.preventDefault();
        const [dr, dc] = map[e.key];
        tryMovePlayer(player.r + dr, player.c + dc);
    });

    document.getElementById('algoSelect').addEventListener('change', (e) => {
        state.algo = e.target.value;
        document.getElementById('heuristicSelect').disabled = (state.algo === 'ucs');
        if (state.mode === 'single') recomputeNpcPath();
        draw();
    });
    document.getElementById('heuristicSelect').addEventListener('change', (e) => {
        state.heuristic = e.target.value;
        if (state.mode === 'single') recomputeNpcPath();
        draw();
    });
    document.getElementById('diagonalToggle').addEventListener('change', (e) => {
        state.diagonal = e.target.checked;
        if (state.mode === 'single') recomputeNpcPath();
        draw();
    });
    document.getElementById('exploredToggle').addEventListener('change', (e) => {
        state.showExplored = e.target.checked;
        draw();
    });
    document.getElementById('speedRange').addEventListener('input', (e) => {
        state.speedMs = parseInt(e.target.value, 10);
        const label = state.speedMs < 120 ? 'cepat' : (state.speedMs > 320 ? 'lambat' : 'sedang');
        document.getElementById('speedLabel').textContent = label;
    });
    document.getElementById('newMapBtn').addEventListener('click', () => {
        if (state.mode !== 'single') return;
        generateMap();
        recomputeNpcPath();
        draw();
    });
    document.getElementById('respawnBtn').addEventListener('click', () => {
        if (state.mode !== 'single') return;
        respawnPositions();
        recomputeNpcPath();
        draw();
    });

    /* ---------- Multiplayer: gameplay ---------- */
    function stopGhostLoop() {
        clearTimeout(multi.tickTimer);
    }

    function nearestAlivePlayer(g) {
        let best = null,
            bestD = Infinity;
        multi.players.forEach(p => {
            if (!p.alive) return;
            const d = Math.abs(p.r - g.r) + Math.abs(p.c - g.c);
            if (d < bestD) {
                bestD = d;
                best = p;
            }
        });
        return best;
    }

    function applyGhostHit(p) {
        const now = performance.now();
        if (p.invulnUntil && now < p.invulnUntil) return;
        p.lives--;
        if (p.lives <= 0) {
            p.lives = 0;
            p.alive = false;
            showToast(p.name + ' kehabisan nyawa!');
        } else {
            showToast(p.name + ' tertangkap! Sisa nyawa: ' + p.lives);
            p.r = p.spawn.r;
            p.c = p.spawn.c;
            p.invulnUntil = now + 1200;
        }
        updateScoreboard();
        checkWinConditions();
    }

    function checkGhostCollisionsForPlayer(p) {
        if (!p.alive) return;
        const now = performance.now();
        if (p.invulnUntil && now < p.invulnUntil) return;
        const hit = multi.ghosts.some(g => g.r === p.r && g.c === p.c);
        if (hit) applyGhostHit(p);
    }

    function movePlayerMulti(p, dr, dc) {
        const nr = p.r + dr,
            nc = p.c + dc;
        if (!isPassable(nr, nc)) return;
        p.r = nr;
        p.c = nc;
        const ci = multi.coins.findIndex(k => k.r === nr && k.c === nc);
        if (ci !== -1) {
            multi.coins.splice(ci, 1);
            p.score++;
        }
        checkGhostCollisionsForPlayer(p);
        updateScoreboard();
        checkWinConditions();
    }

    function ghostTickMulti() {
        if (!multi.active || multi.over) return;
        const heuristicFn = currentHeuristicFn();
        multi.ghosts.forEach(g => {
            const target = nearestAlivePlayer(g);
            if (!target) return;
            const res = search(g, target, state.diagonal, heuristicFn);
            if (res.path && res.path.length > 1) {
                g.r = res.path[1].r;
                g.c = res.path[1].c;
            }
        });
        multi.ghosts.forEach(g => {
            multi.players.forEach(p => {
                if (p.alive && p.r === g.r && p.c === g.c) applyGhostHit(p);
            });
        });
        draw();
        checkWinConditions();
        if (multi.active && !multi.over) {
            multi.tickTimer = setTimeout(ghostTickMulti, state.speedMs);
        }
    }

    function endRound(title, body) {
        multi.over = true;
        multi.active = false;
        stopGhostLoop();
        stopMusic();
        document.getElementById('roundEndTitle').textContent = title;
        document.getElementById('roundEndBody').textContent = body;
        document.getElementById('roundEndOverlay').classList.remove('hidden');
    }

    function endRoundByScore() {
        const alive = multi.players.filter(p => p.alive);
        const pool = alive.length ? alive : multi.players;
        const maxScore = Math.max(...pool.map(p => p.score));
        const winners = pool.filter(p => p.score === maxScore);
        const names = winners.map(w => w.name).join(', ');
        const title = winners.length > 1 ? 'Seri!' : (winners[0].name + ' Menang!');
        const body = 'Semua koin terkumpul. ' + (winners.length > 1 ? ('Pemain ' + names + ' seri') : names) + ' dengan ' + maxScore + ' koin.';
        endRound(title, body);
    }

    function checkWinConditions() {
        if (multi.over) return;
        if (multi.coins.length === 0) {
            endRoundByScore();
            return;
        }
        const alivePlayers = multi.players.filter(p => p.alive);
        if (alivePlayers.length === 0) {
            endRound('Semua Pemain Kalah', 'Hantu menangkap semua pemain. Coba lagi!');
        } else if (multi.players.length > 1 && alivePlayers.length === 1) {
            endRound(alivePlayers[0].name + ' Menang!', alivePlayers[0].name + ' adalah pemain terakhir yang bertahan dengan ' + alivePlayers[0].score + ' koin.');
        }
    }

    function hideRoundEnd() {
        document.getElementById('roundEndOverlay').classList.add('hidden');
    }

    function updateScoreboard() {
        const el = document.getElementById('scoreboardList');
        if (!el) return;
        el.innerHTML = multi.players.map(p => {
            const hearts = Array.from({
                length: 3
            }, (_, i) => i < p.lives ? '❤️' : '<span class="lost">❤️</span>').join('');
            return '<div class="score-row ' + (p.alive ? '' : 'eliminated') + '">' +
                '<span class="player-dot" style="background:' + p.color + '"></span>' +
                '<span class="score-name">' + p.name + '</span>' +
                '<span class="hearts">' + hearts + '</span>' +
                '<span class="score-coins">\uD83E\uDE99 ' + p.score + '</span>' +
                '</div>';
        }).join('') + '<div class="desc" style="margin-top:8px;">Koin tersisa: <b>' + multi.coins.length + '</b></div>';
    }

    function renderPlayerControlsUI() {
        const container = document.getElementById('playerControlsList');
        if (!container) return;
        container.innerHTML = multi.players.map((p, idx) => {
            const dirs = [
                ['up', 'Atas'],
                ['left', 'Kiri'],
                ['down', 'Bawah'],
                ['right', 'Kanan']
            ];
            const keys = dirs.map(([dir, label]) =>
                '<div class="key-btn" data-idx="' + idx + '" data-dir="' + dir + '">' +
                '<span class="k-label">' + label + '</span><span class="k-val">' + keyLabel(p.controls[dir]) + '</span></div>'
            ).join('');
            return '<div class="player-row">' +
                '<div class="player-row-head"><span class="player-dot" style="background:' + p.color + '"></span>' + p.name + '</div>' +
                '<div class="key-grid">' + keys + '</div>' +
                '</div>';
        }).join('');
        container.querySelectorAll('.key-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                container.querySelectorAll('.key-btn').forEach(b => b.classList.remove('listening'));
                multi.listeningFor = {
                    idx: parseInt(btn.dataset.idx, 10),
                    dir: btn.dataset.dir
                };
                btn.classList.add('listening');
                btn.querySelector('.k-val').textContent = '...';
            });
        });
    }

    function startMultiplayerRound() {
        if (multi.over) resetMultiplayerRound();
        multi.active = true;
        hideRoundEnd();
        playMusic();
        stopGhostLoop();
        ghostTickMulti();
    }

    function resetMultiplayerRound() {
        stopGhostLoop();
        generateMultiplayerMap();
        renderPlayerControlsUI();
        updateScoreboard();
        hideRoundEnd();
        draw();
    }

    function setMode(newMode) {
        state.mode = newMode;
        const isMulti = newMode === 'multi';
        document.getElementById('multiSetupPanel').style.display = isMulti ? 'block' : 'none';
        document.getElementById('scoreboardPanel').style.display = isMulti ? 'block' : 'none';
        document.getElementById('liveStatsPanel').style.display = isMulti ? 'none' : 'block';
        document.getElementById('experimentPanel').style.display = isMulti ? 'none' : 'block';
        document.getElementById('singleMapButtons').style.display = isMulti ? 'none' : 'flex';
        document.getElementById('howToText').innerHTML = isMulti ?
            'Setiap pemain punya tombol gerak sendiri (atur di panel Multiplayer). Kumpulkan koin kuning dan hindari hantu merah. Setiap pemain punya <b>3 nyawa</b> — tertangkap hantu mengurangi 1 nyawa dan pemain kembali ke titik awal. Ronde berakhir saat semua koin habis atau hanya tersisa satu pemain yang bertahan.' :
            'Gerakkan pemain dengan <b>WASD</b> atau tombol panah (↑↓←→) di keyboard. NPC akan terus menghitung ulang jalur terpendek menuju posisi pemain saat ini.';
        document.getElementById('modeHint').textContent = isMulti ?
            'Setiap pemain memakai tombolnya sendiri (lihat panel Multiplayer). Klik "Mulai Permainan" untuk memulai ronde.' :
            'Klik petak yang bisa dilewati untuk memindahkan pemain. Panah keyboard (↑↓←→) juga bisa dipakai.';

        if (isMulti) {
            stopSingleLoop();
            multi.numPlayers = parseInt(document.getElementById('playerCountSelect').value, 10);
            generateMultiplayerMap();
            renderPlayerControlsUI();
            updateScoreboard();
            hideRoundEnd();
            draw();
        } else {
            stopGhostLoop();
            stopMusic();
            hideRoundEnd();
            generateMap();
            document.getElementById('heuristicSelect').disabled = (state.algo === 'ucs');
            recomputeNpcPath();
            draw();
            startSingleLoop();
        }
    }

    document.getElementById('modeSelect').addEventListener('change', (e) => {
        setMode(e.target.value);
    });
    document.getElementById('playerCountSelect').addEventListener('change', (e) => {
        multi.numPlayers = parseInt(e.target.value, 10);
        resetMultiplayerRound();
    });
    document.getElementById('startRoundBtn').addEventListener('click', () => {
        startMultiplayerRound();
    });
    document.getElementById('resetRoundBtn').addEventListener('click', () => {
        resetMultiplayerRound();
    });
    document.getElementById('roundEndPlayAgainBtn').addEventListener('click', () => {
        resetMultiplayerRound();
    });

    /* ---------- Layar penuh ---------- */
    document.getElementById('fullscreenBtn').addEventListener('click', () => {
        const stageEl = document.querySelector('.stage');
        if (!document.fullscreenElement) {
            stageEl.requestFullscreen().catch(() => showToast('Layar penuh tidak didukung di browser ini.'));
        } else {
            document.exitFullscreen();
        }
    });
    document.addEventListener('fullscreenchange', () => {
        const btn = document.getElementById('fullscreenBtn');
        btn.textContent = document.fullscreenElement ? '⛶ Keluar Layar Penuh' : '⛶ Layar Penuh';
    });

    /* ---------- Musik (tidak diputar otomatis) ---------- */
    const bgm = document.getElementById('bgm');
    let musicOn = false;

    function updateMusicBtn() {
        const btn = document.getElementById('musicToggleBtn');
        btn.textContent = musicOn ? '🔊 Musik' : '🔇 Musik';
        btn.classList.toggle('on', musicOn);
        btn.setAttribute('aria-pressed', String(musicOn));
    }

    function playMusic() {
        musicOn = true;
        bgm.play().catch(() => {});
        updateMusicBtn();
    }

    function stopMusic() {
        musicOn = false;
        bgm.pause();
        updateMusicBtn();
    }

    document.getElementById('musicToggleBtn').addEventListener('click', () => {
        if (musicOn) stopMusic();
        else playMusic();
    });

    /* ---------- Eksperimen heuristik ---------- */
    function sampleStartGoal() {
        let best = null,
            bestDist = -1;
        for (let i = 0; i < 25; i++) {
            const a = passableCells[Math.floor(Math.random() * passableCells.length)];
            const b = passableCells[Math.floor(Math.random() * passableCells.length)];
            const d = Math.max(Math.abs(a.r - b.r), Math.abs(a.c - b.c));
            if (d > bestDist) {
                bestDist = d;
                best = [a, b];
            }
        }
        return {
            start: best[0],
            goal: best[1]
        };
    }

    function avg(arr) {
        return arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0;
    }

    function runExperiment() {
        const trials = Math.max(5, Math.min(200, parseInt(document.getElementById('trialCount').value, 10) || 30));
        const names = ['manhattan', 'euclidean', 'chebyshev', 'octile'];
        const agg = {
            ucs: {
                nodes: [],
                time: []
            }
        };
        names.forEach(n => agg[n] = {
            nodes: [],
            time: [],
            ratio: [],
            optimal: 0
        });

        let completed = 0;
        for (let i = 0; i < trials; i++) {
            const {
                start,
                goal
            } = sampleStartGoal();
            const ucsRes = search(start, goal, state.diagonal, HEURISTICS.zero);
            if (!ucsRes.path) continue;
            agg.ucs.nodes.push(ucsRes.nodesExpanded);
            agg.ucs.time.push(ucsRes.timeMs);
            names.forEach(n => {
                const res = search(start, goal, state.diagonal, HEURISTICS[n]);
                agg[n].nodes.push(res.nodesExpanded);
                agg[n].time.push(res.timeMs);
                const ratio = res.path ? res.cost / ucsRes.cost : Infinity;
                agg[n].ratio.push(ratio);
                if (res.path && Math.abs(res.cost - ucsRes.cost) < 1e-6) agg[n].optimal++;
            });
            completed++;
        }
        renderExperimentResults(agg, completed, names);
    }

    function renderExperimentResults(agg, n, names) {
        const rows = [{
            key: 'ucs',
            label: 'UCS (baseline)'
        }].concat(names.map(x => ({
            key: x,
            label: x
        })));
        let html = '<table class="results"><thead><tr><th>Metode</th><th>Rata² node</th><th>Waktu (ms)</th><th>Rasio biaya</th><th>% optimal</th></tr></thead><tbody>';
        const maxNodes = Math.max(...rows.map(row => avg(agg[row.key].nodes)));

        rows.forEach(row => {
            const d = agg[row.key];
            const nodesAvg = avg(d.nodes);
            const timeAvg = avg(d.time);
            const ratioAvg = row.key === 'ucs' ? 1 : avg(d.ratio.filter(x => isFinite(x)));
            const optPct = row.key === 'ucs' ? 100 : Math.round(100 * d.optimal / n);
            html += `<tr><td>${row.label}</td><td>${nodesAvg.toFixed(1)}</td><td>${timeAvg.toFixed(3)}</td><td>${ratioAvg.toFixed(3)}</td><td>${optPct}%${optPct<100?'<span class="badge warn">tidak selalu optimal</span>':''}</td></tr>`;
        });
        html += '</tbody></table>';

        html += '<div style="margin-top:12px;">';
        rows.forEach(row => {
            const nodesAvg = avg(agg[row.key].nodes);
            const pct = maxNodes > 0 ? (nodesAvg / maxNodes * 100) : 0;
            html += `<div class="bar-row"><span class="bar-label">${row.label}</span><div class="bar-track"><div class="bar-fill ${row.key==='ucs'?'ucs':''}" style="width:${pct.toFixed(1)}%"></div></div><span class="bar-value">${nodesAvg.toFixed(0)}</span></div>`;
        });
        html += '</div>';

        document.getElementById('experimentResults').innerHTML = html;

        // simpulan otomatis
        let candidate = null;
        names.forEach(nm => {
            const optPct = 100 * agg[nm].optimal / n;
            const nodesAvg = avg(agg[nm].nodes);
            if (optPct >= 99.5) {
                if (!candidate || nodesAvg < candidate.nodesAvg) candidate = {
                    name: nm,
                    nodesAvg
                };
            }
        });
        const ucsAvg = avg(agg.ucs.nodes);
        const modeLabel = state.diagonal ? '8 arah (diagonal diizinkan)' : '4 arah (tanpa diagonal)';
        let text;
        if (candidate) {
            const reduction = ucsAvg > 0 ? (100 * (1 - candidate.nodesAvg / ucsAvg)).toFixed(1) : '0';
            text = `Mode gerak: <b>${modeLabel}</b>, ${n} percobaan. Heuristik <b>${candidate.name}</b> tetap optimal 100% dan mengeksplorasi node paling sedikit (\u2248${reduction}% lebih hemat dibanding UCS). `;
            if (state.diagonal) {
                text += 'Ini sesuai teori: pada gerak 8 arah, Octile Distance adalah estimasi jarak sebenarnya yang paling ketat namun tetap tidak pernah melebih-lebihkan (admissible), sehingga paling efisien. Manhattan Distance cenderung melebih-lebihkan jarak diagonal sehingga berisiko tidak optimal, sedangkan Euclidean/Chebyshev tetap optimal tapi kurang ketat (mengeksplorasi lebih banyak node).';
            } else {
                text += 'Ini sesuai teori: pada gerak 4 arah, Manhattan Distance sama persis dengan jarak minimum sebenarnya (paling ketat & tetap admissible), sehingga paling efisien di antara heuristik yang diuji.';
            }
        } else {
            text = `Mode gerak: <b>${modeLabel}</b>, ${n} percobaan. Tidak ada heuristik yang 100% optimal pada sesi ini — coba tambah jumlah percobaan atau buat peta baru untuk sampel yang lebih representatif.`;
        }
        document.getElementById('experimentConclusion').innerHTML = `<div class="conclusion">${text}</div>`;
    }

    document.getElementById('runExperimentBtn').addEventListener('click', runExperiment);

    /* ---------- Inisialisasi ---------- */
    state.mode = 'single';
    multi.numPlayers = parseInt(document.getElementById('playerCountSelect').value, 10) || 2;
    generateMap();
    document.getElementById('heuristicSelect').disabled = (state.algo === 'ucs');
    recomputeNpcPath();
    draw();
    startSingleLoop();
    // Musik TIDAK diputar otomatis — hanya lewat tombol musik atau saat ronde multiplayer dimulai.

})();