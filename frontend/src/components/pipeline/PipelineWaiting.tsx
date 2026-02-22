/**
 * PipelineWaiting — Finance-themed mini-game shown during the 90-second reconciliation wait
 *
 * Theme: "Mercury Markets" — a playful stock-ticker mini-game.
 * - A small pixel-art trader character runs left/right on a scrolling ticker tape
 * - They jump over red candles (discrepancies) and collect green coins (matches)
 * - Score = matches caught. High score is stored in localStorage.
 * - Keyboard: Space / ArrowUp to jump
 * - Mobile: tap anywhere to jump
 *
 * The game is entirely canvas-based (no libraries) to keep the bundle small.
 * It fades out automatically when the pipeline sends a "done" event.
 */
import { useEffect, useRef, useCallback, useState } from 'react'
import './PipelineWaiting.css'

interface Props {
    progress: number   // 0–100 from WebSocket
    stage: string   // current stage label
    label: string   // human-readable label
}

// ── Mini-game constants ───────────────────────────────────────────────────────

const W = 640
const H = 180
const GROUND_Y = 140
const GRAVITY = 0.55
const JUMP_VEL = -12
const SCROLL_SPEED_BASE = 3.5
const OBSTACLE_INTERVAL_MIN = 60   // frames
const OBSTACLE_INTERVAL_MAX = 110

// Colour palette — financial dark theme
const PALETTE = {
    bg: '#0a0f1e',
    ground: '#1e293b',
    ticker: '#0f172a',
    green: '#10b981',
    red: '#ef4444',
    gold: '#f59e0b',
    text: '#64748b',
    player: '#6366f1',
    playerEye: '#f1f5f9',
    shadow: 'rgba(99,102,241,0.3)',
}

// ── Mini-game engine ──────────────────────────────────────────────────────────

type Obstacle = { x: number; kind: 'candle' | 'coin'; height: number; collected?: boolean }

function createGame(canvas: HTMLCanvasElement) {
    const ctx = canvas.getContext('2d')!
    let frame = 0
    let score = 0
    let highScore = parseInt(localStorage.getItem('ventro_hiscore') ?? '0', 10)
    let raf = 0
    let dead = false

    // Player state
    let py = GROUND_Y   // y position (top of player)
    let vy = 0          // vertical velocity
    let onGround = true
    let runFrame = 0    // animation frame counter

    // Obstacles
    let obstacles: Obstacle[] = []
    let nextObstacle = 70

    // Ticker symbols scrolling in background
    const symbols = ['MATCH+3.2%', 'DELTA−0.8%', 'AUDIT+1.1%', 'LEDGR+5.0%',
        'SAMR+2.4%', 'RECON+0.3%', 'INVCE−1.3%', 'PORDER+4%']
    let tickerX = W
    let scrollSpeed = SCROLL_SPEED_BASE

    function jump() {
        if (onGround && !dead) {
            vy = JUMP_VEL
            onGround = false
        }
    }

    // ── Draw helpers ──────────────────────────────────────────────────────────

    function drawGround() {
        ctx.fillStyle = PALETTE.ground
        ctx.fillRect(0, GROUND_Y + 28, W, H)
        // Dashed line
        ctx.setLineDash([8, 6])
        ctx.strokeStyle = '#1e3a5f'
        ctx.lineWidth = 1
        ctx.beginPath()
        ctx.moveTo(0, GROUND_Y + 28)
        ctx.lineTo(W, GROUND_Y + 28)
        ctx.stroke()
        ctx.setLineDash([])
    }

    function drawTicker() {
        const tickerText = symbols.join('  ·  ') + '  ·  '
        ctx.font = '11px "Courier New", monospace'
        ctx.fillStyle = '#1e3a5f'
        ctx.fillText(tickerText.repeat(3), tickerX, GROUND_Y + 44)
        tickerX -= scrollSpeed * 0.4
        const textW = ctx.measureText(tickerText).width
        if (tickerX < -textW) tickerX += textW
    }

    function drawPlayer() {
        const px = 80
        const pw = 24
        const ph = 28

        // Shadow
        ctx.fillStyle = PALETTE.shadow
        ctx.ellipse(px + pw / 2, GROUND_Y + 30, 14, 5, 0, 0, Math.PI * 2)
        ctx.fill()

        // Body (trader in suit)
        ctx.fillStyle = PALETTE.player
        ctx.beginPath()
        ctx.roundRect(px, py, pw, ph, 4)
        ctx.fill()

        // Briefcase (oscillates with run frame)
        const briefY = py + ph - 6 + (runFrame < 8 ? 1 : 0)
        ctx.fillStyle = PALETTE.gold
        ctx.fillRect(px + pw - 5, briefY, 7, 5)
        ctx.fillStyle = '#92400e'
        ctx.fillRect(px + pw - 3, briefY - 2, 3, 2)

        // Eye
        ctx.fillStyle = PALETTE.playerEye
        ctx.beginPath()
        ctx.arc(px + pw - 5, py + 8, 3, 0, Math.PI * 2)
        ctx.fill()

        // Legs animation
        const leg1Y = py + ph
        const leg2Y = py + ph
        const leg1X = runFrame < 8 ? px + 4 : px + 10
        const leg2X = runFrame < 8 ? px + 10 : px + 4
        ctx.strokeStyle = PALETTE.player
        ctx.lineWidth = 4
        ctx.lineCap = 'round'
        ctx.beginPath()
        ctx.moveTo(px + 6, leg1Y); ctx.lineTo(leg1X, leg1Y + 10)
        ctx.moveTo(px + 14, leg2Y); ctx.lineTo(leg2X, leg2Y + 10)
        ctx.stroke()

        runFrame = (runFrame + 1) % 16
    }

    function drawObstacles() {
        for (const ob of obstacles) {
            if (ob.kind === 'candle') {
                // Red candle (bearish)
                ctx.fillStyle = PALETTE.red
                ctx.fillRect(ob.x, GROUND_Y + 28 - ob.height, 18, ob.height)
                ctx.fillStyle = '#fca5a5'
                ctx.fillRect(ob.x + 6, GROUND_Y + 28 - ob.height - 10, 6, 10)
            } else {
                // Gold coin (match)
                if (ob.collected) continue
                ctx.fillStyle = PALETTE.gold
                ctx.beginPath()
                ctx.arc(ob.x + 10, GROUND_Y - 20, 10, 0, Math.PI * 2)
                ctx.fill()
                ctx.fillStyle = '#fef3c7'
                ctx.font = 'bold 9px sans-serif'
                ctx.textAlign = 'center'
                ctx.fillText('✓', ob.x + 10, GROUND_Y - 16)
                ctx.textAlign = 'left'
            }
        }
    }

    function drawHUD() {
        // Score
        ctx.font = 'bold 14px "Courier New", monospace'
        ctx.fillStyle = PALETTE.green
        ctx.fillText(`MATCHES: ${score}`, 12, 22)
        // High score
        ctx.fillStyle = PALETTE.gold
        ctx.fillText(`BEST: ${highScore}`, 12, 40)
        // Controls hint
        ctx.fillStyle = PALETTE.text
        ctx.font = '10px sans-serif'
        ctx.fillText('SPACE / TAP to jump over discrepancies', W - 10, 22)
        // TODO: align right properly
    }

    function drawDeathScreen() {
        ctx.fillStyle = 'rgba(239,68,68,0.15)'
        ctx.fillRect(0, 0, W, H)
        ctx.fillStyle = PALETTE.red
        ctx.font = 'bold 20px sans-serif'
        ctx.textAlign = 'center'
        ctx.fillText('DISCREPANCY DETECTED! PRESS SPACE TO RETRY', W / 2, H / 2)
        ctx.textAlign = 'left'
    }

    // ── Collision detection ───────────────────────────────────────────────────

    function checkCollisions() {
        const px = 80; const pw = 24; const ph = 28
        for (const ob of obstacles) {
            if (ob.kind === 'candle') {
                const hit =
                    px + pw > ob.x + 4 &&
                    px < ob.x + 14 &&
                    py + ph > GROUND_Y + 28 - ob.height
                if (hit) { dead = true }
            } else if (!ob.collected) {
                const coinX = ob.x + 10; const coinY = GROUND_Y - 20
                const dist = Math.hypot(px + pw / 2 - coinX, py + ph / 2 - coinY)
                if (dist < 20) {
                    ob.collected = true
                    score++
                    if (score > highScore) {
                        highScore = score
                        localStorage.setItem('ventro_hiscore', String(highScore))
                    }
                }
            }
        }
    }

    // ── Main loop ─────────────────────────────────────────────────────────────

    function reset() {
        py = GROUND_Y; vy = 0; onGround = true; dead = false
        obstacles = []; nextObstacle = 70; frame = 0; score = 0
        scrollSpeed = SCROLL_SPEED_BASE
    }

    function tick() {
        raf = requestAnimationFrame(tick)
        frame++

        ctx.fillStyle = PALETTE.bg
        ctx.fillRect(0, 0, W, H)

        drawTicker()
        drawGround()

        if (!dead) {
            // Physics
            vy += GRAVITY
            py += vy
            if (py >= GROUND_Y) { py = GROUND_Y; vy = 0; onGround = true }

            // Spawn obstacles
            nextObstacle--
            if (nextObstacle <= 0) {
                const kind = Math.random() < 0.35 ? 'coin' : 'candle'
                obstacles.push({
                    x: W + 20,
                    kind,
                    height: kind === 'candle' ? 20 + Math.random() * 30 : 0,
                })
                nextObstacle = OBSTACLE_INTERVAL_MIN +
                    Math.floor(Math.random() * (OBSTACLE_INTERVAL_MAX - OBSTACLE_INTERVAL_MIN))
            }

            // Move obstacles
            scrollSpeed = SCROLL_SPEED_BASE + frame / 1200
            for (const ob of obstacles) ob.x -= scrollSpeed
            obstacles = obstacles.filter(ob => ob.x > -40)

            checkCollisions()
        }

        drawObstacles()
        drawPlayer()
        drawHUD()
        if (dead) drawDeathScreen()
    }

    const handleKey = (e: KeyboardEvent) => {
        if (e.code === 'Space' || e.code === 'ArrowUp') {
            e.preventDefault()
            if (dead) reset()
            else jump()
        }
    }
    const handleTouch = () => { if (dead) reset(); else jump() }

    window.addEventListener('keydown', handleKey)
    canvas.addEventListener('click', handleTouch)
    tick()

    return () => {
        cancelAnimationFrame(raf)
        window.removeEventListener('keydown', handleKey)
        canvas.removeEventListener('click', handleTouch)
    }
}

// ── React component ───────────────────────────────────────────────────────────

const STAGE_ICONS: Record<string, string> = {
    initializing: '⚙️',
    extracting_documents: '📄',
    quantitative_check: '🔢',
    compliance_check: '⚖️',
    confidence_assurance: '🛡️',
    reconciliation: '🔗',
    drafting_workpaper: '📋',
    completed: '✅',
}

const ALL_STAGES = [
    'extracting_documents',
    'quantitative_check',
    'compliance_check',
    'confidence_assurance',
    'reconciliation',
    'drafting_workpaper',
]

export default function PipelineWaiting({ progress, stage, label }: Props) {
    const canvasRef = useRef<HTMLCanvasElement>(null)
    const [scoreDisplay, setScoreDisplay] = useState(0)

    useEffect(() => {
        const canvas = canvasRef.current
        if (!canvas) return
        const cleanup = createGame(canvas)
        return cleanup
    }, [])

    const stageIdx = ALL_STAGES.indexOf(stage)

    return (
        <div className="pw-container">
            {/* Header */}
            <div className="pw-header">
                <div className="pw-spinner" />
                <div>
                    <div className="pw-title">AI Pipeline Running</div>
                    <div className="pw-subtitle">
                        {STAGE_ICONS[stage] ?? '⏳'} {label || 'Processing…'}
                    </div>
                </div>
            </div>

            {/* Progress bar */}
            <div className="pw-progress-track">
                <div
                    className="pw-progress-fill"
                    style={{ width: `${progress}%` }}
                />
                <span className="pw-progress-pct">{progress}%</span>
            </div>

            {/* Agent stage bubbles */}
            <div className="pw-stages">
                {ALL_STAGES.map((s, i) => (
                    <div
                        key={s}
                        className={`pw-stage-dot ${i < stageIdx ? 'pw-stage-dot--done' :
                                i === stageIdx ? 'pw-stage-dot--active' : ''
                            }`}
                        title={s.replace(/_/g, ' ')}
                    >
                        {STAGE_ICONS[s]}
                    </div>
                ))}
            </div>

            {/* Mini-game */}
            <div className="pw-game-wrapper">
                <div className="pw-game-label">
                    While you wait — dodge the discrepancies, collect the matches
                </div>
                <canvas
                    ref={canvasRef}
                    width={W}
                    height={H}
                    className="pw-canvas"
                />
                <div className="pw-game-hint">SPACE or click to jump</div>
            </div>

            {/* Fun fact ticker */}
            <div className="pw-fact-ticker">
                <span>
                    💡 AP teams spend avg. 14 days per month on manual matching ·
                    Ventro reduces this to under 90 seconds ·
                    The Confidence Assurance layer catches errors that LLMs alone miss ·
                    Three-way matching prevents 73% of invoice fraud attempts ·
                    Your documents never leave your infrastructure ·
                </span>
            </div>
        </div>
    )
}
