// BTC Trading Dashboard JavaScript

// Global state
let socket = null;
let priceChart = null;
let lastPrice = null;
let currentBacktestJob = null;
let priceUpdateInterval = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    initializeTheme();
    initializeSocket();
    initializePriceChart();
    loadInitialData();
    setupEventListeners();
    setupBacktestListeners();
    initTradingConfig();
    startPriceUpdates();
    startClock();
    setupThemeToggle();
});

// ═══════════════════════════════════════════════════════════════
// SOCKET.IO CONNECTION
// ═══════════════════════════════════════════════════════════════

function initializeSocket() {
    socket = io();

    socket.on('connect', function() {
        console.log('Connected to server');
        updateConnectionStatus(true);
        socket.emit('request_update');
    });

    socket.on('disconnect', function() {
        console.log('Disconnected from server');
        updateConnectionStatus(false);
    });

    socket.on('price_update', function(data) {
        updateCurrentPrice(data.price);
    });

    socket.on('strategy_prediction', function(data) {
        handleStrategyPrediction(data);
    });

    socket.on('strategy_result', function(data) {
        handleStrategyResult(data);
    });

    socket.on('strategy_status', function(data) {
        handleStrategyStatus(data);
    });

    socket.on('mid_period_check', function(data) {
        handleMidPeriodCheck(data);
    });

    socket.on('strategies_update', function(data) {
        updateStrategiesDisplay(data);
    });

    socket.on('backtest_progress', function(data) {
        updateBacktestProgress(data);
    });

    socket.on('backtest_complete', function(data) {
        handleBacktestComplete(data);
    });

    socket.on('backfill_complete', function(data) {
        handleBackfillComplete(data);
    });

    socket.on('refresh_chart', function() {
        loadHistoricalData();
    });

    socket.on('gap_filled', function(data) {
        handleGapFilled(data);
    });

    socket.on('bet_placed', function(data) {
        handleBetPlaced(data);
    });

    socket.on('position_closed', function(data) {
        handlePositionClosed(data);
    });
}

function updateConnectionStatus(connected) {
    const badge = document.getElementById('connection-status');
    if (connected) {
        badge.textContent = 'Connected';
        badge.className = 'badge bg-success connected';
    } else {
        badge.textContent = 'Disconnected';
        badge.className = 'badge bg-danger disconnected';
    }
}

// ═══════════════════════════════════════════════════════════════
// 24-HOUR CLOCK
// ═══════════════════════════════════════════════════════════════

function startClock() {
    updateClock();
    setInterval(updateClock, 1000);
}

function updateClock() {
    const now = new Date();
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    const seconds = String(now.getSeconds()).padStart(2, '0');
    document.getElementById('current-time').textContent = `${hours}:${minutes}:${seconds}`;
}

// ═══════════════════════════════════════════════════════════════
// THEME MANAGEMENT
// ═══════════════════════════════════════════════════════════════

function initializeTheme() {
    const savedTheme = localStorage.getItem('theme') || 'dark';
    applyTheme(savedTheme);
}

function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    updateThemeIcon(theme);

    // Update chart if it exists
    if (priceChart) {
        updateChartTheme(theme);
    }
}

function updateThemeIcon(theme) {
    const icon = document.getElementById('theme-icon');
    if (icon) {
        icon.textContent = theme === 'dark' ? '🌙' : '☀️';
    }
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'dark';
    const newTheme = current === 'dark' ? 'light' : 'dark';
    applyTheme(newTheme);
    localStorage.setItem('theme', newTheme);
}

function setupThemeToggle() {
    const toggleButton = document.getElementById('theme-toggle');
    if (toggleButton) {
        toggleButton.addEventListener('click', toggleTheme);
    }
}

function updateChartTheme(theme) {
    if (!priceChart) return;

    const isDark = theme === 'dark';
    const ctx = document.getElementById('priceChart').getContext('2d');

    // Create new gradient based on theme
    const gradient = ctx.createLinearGradient(0, 0, 0, 400);
    if (isDark) {
        gradient.addColorStop(0, 'rgba(0, 212, 170, 0.4)');
        gradient.addColorStop(0.5, 'rgba(0, 212, 170, 0.1)');
        gradient.addColorStop(1, 'rgba(0, 212, 170, 0)');
    } else {
        gradient.addColorStop(0, 'rgba(0, 212, 170, 0.3)');
        gradient.addColorStop(0.5, 'rgba(0, 212, 170, 0.08)');
        gradient.addColorStop(1, 'rgba(0, 212, 170, 0)');
    }

    // Update chart colors
    priceChart.data.datasets[0].backgroundColor = gradient;
    priceChart.data.datasets[0].borderColor = '#00d4aa';

    priceChart.options.scales.x.grid.color = isDark ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.05)';
    priceChart.options.scales.x.grid.borderColor = isDark ? '#2d3748' : '#dee2e6';
    priceChart.options.scales.x.ticks.color = isDark ? '#6c757d' : '#495057';

    priceChart.options.scales.y.grid.color = isDark ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.05)';
    priceChart.options.scales.y.grid.borderColor = isDark ? '#2d3748' : '#dee2e6';
    priceChart.options.scales.y.ticks.color = isDark ? '#a0a0a0' : '#495057';

    priceChart.options.plugins.tooltip.backgroundColor = isDark ? 'rgba(30, 35, 48, 0.95)' : 'rgba(255, 255, 255, 0.95)';
    priceChart.options.plugins.tooltip.titleColor = isDark ? '#a0a0a0' : '#495057';
    priceChart.options.plugins.tooltip.bodyColor = isDark ? '#ffffff' : '#212529';
    priceChart.options.plugins.tooltip.borderColor = isDark ? '#2d3748' : '#dee2e6';

    priceChart.update();
}

// ═══════════════════════════════════════════════════════════════
// INITIAL DATA LOADING
// ═══════════════════════════════════════════════════════════════

function loadInitialData() {
    // Load current price
    fetch('/api/current_price')
        .then(response => response.json())
        .then(data => {
            updateCurrentPrice(data.price);
        })
        .catch(error => console.error('Error loading price:', error));

    // Load strategies status
    fetch('/api/strategies')
        .then(response => response.json())
        .then(data => {
            updateStrategiesDisplay(data);
        })
        .catch(error => console.error('Error loading strategies:', error));

    // Load historical price data
    loadHistoricalData();

    // Load activity feed
    loadActivityFeed();
}

function loadHistoricalData() {
    fetch('/api/history?limit=100')
        .then(response => response.json())
        .then(data => {
            updatePriceChart(data.history);
        })
        .catch(error => console.error('Error loading history:', error));
}

function loadActivityFeed() {
    fetch('/api/activity?limit=50')
        .then(response => response.json())
        .then(data => {
            displayActivityFeed(data.items);
        })
        .catch(error => console.error('Error loading activity feed:', error));
}

// ═══════════════════════════════════════════════════════════════
// PRICE DISPLAY
// ═══════════════════════════════════════════════════════════════

function startPriceUpdates() {
    // Update price every 2 seconds (less violent)
    priceUpdateInterval = setInterval(function() {
        fetch('/api/current_price')
            .then(response => response.json())
            .then(data => {
                // Only update if price actually changed
                if (lastPrice === null || Math.abs(data.price - lastPrice) > 0.01) {
                    updateCurrentPrice(data.price);
                }
            })
            .catch(error => console.error('Error fetching price:', error));
    }, 2000);
}

function updateCurrentPrice(price) {
    const priceElement = document.getElementById('header-price');
    const changeElement = document.getElementById('header-price-change');

    // Determine direction and update change badge
    if (lastPrice !== null) {
        const change = ((price - lastPrice) / lastPrice) * 100;

        // Update change badge
        changeElement.textContent = `${change >= 0 ? '+' : ''}${change.toFixed(2)}%`;
        changeElement.className = `badge ${change >= 0 ? 'positive bg-success' : 'negative bg-danger'}`;

        // Update price color briefly
        if (price > lastPrice) {
            priceElement.classList.remove('price-down');
            priceElement.classList.add('price-up');
        } else if (price < lastPrice) {
            priceElement.classList.remove('price-up');
            priceElement.classList.add('price-down');
        }

        // Remove color classes after brief flash
        setTimeout(() => {
            priceElement.classList.remove('price-up', 'price-down');
        }, 600);
    }

    // Smooth number animation
    animateNumberChange(priceElement, price);

    lastPrice = price;
}

function animateNumberChange(element, targetPrice) {
    const currentText = element.textContent.replace(/[$,]/g, '');
    const currentPrice = parseFloat(currentText) || targetPrice;

    // Format prices
    const formatPrice = (price) => `$${price.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;

    // If the difference is tiny, just update directly
    if (Math.abs(targetPrice - currentPrice) < 0.01) {
        element.textContent = formatPrice(targetPrice);
        return;
    }

    // Use requestAnimationFrame for smooth 60fps animation
    const startTime = performance.now();
    const duration = 800; // 800ms smooth animation
    const startPrice = currentPrice;
    const priceChange = targetPrice - startPrice;

    function animate(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);

        // Easing function for smooth deceleration (ease-out)
        const easeOutQuad = progress * (2 - progress);

        const currentValue = startPrice + (priceChange * easeOutQuad);
        element.textContent = formatPrice(currentValue);

        if (progress < 1) {
            requestAnimationFrame(animate);
        } else {
            // Ensure final value is exact
            element.textContent = formatPrice(targetPrice);
        }
    }

    requestAnimationFrame(animate);
}

// ═══════════════════════════════════════════════════════════════
// PRICE CHART
// ═══════════════════════════════════════════════════════════════

function initializePriceChart() {
    const ctx = document.getElementById('priceChart').getContext('2d');

    // Create gradient
    const gradient = ctx.createLinearGradient(0, 0, 0, 400);
    gradient.addColorStop(0, 'rgba(0, 212, 170, 0.4)');
    gradient.addColorStop(0.5, 'rgba(0, 212, 170, 0.1)');
    gradient.addColorStop(1, 'rgba(0, 212, 170, 0)');

    priceChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'BTC Price',
                data: [],
                borderColor: '#00d4aa',
                backgroundColor: gradient,
                borderWidth: 3,
                tension: 0.4,
                fill: true,
                pointRadius: 0,
                pointHoverRadius: 6,
                pointHoverBackgroundColor: '#00d4aa',
                pointHoverBorderColor: '#fff',
                pointHoverBorderWidth: 2
            },
            // Pattern Strategy Trade Markers
            {
                label: 'Pattern UP ✓',
                data: [],
                borderColor: '#00d4aa',
                backgroundColor: '#00d4aa',
                pointStyle: 'triangle',
                pointRadius: 8,
                pointRotation: 0,
                showLine: false,
                order: 1
            },
            {
                label: 'Pattern UP ✗',
                data: [],
                borderColor: '#00d4aa',
                backgroundColor: 'transparent',
                pointBorderWidth: 2,
                pointStyle: 'triangle',
                pointRadius: 8,
                pointRotation: 0,
                showLine: false,
                order: 1
            },
            {
                label: 'Pattern DOWN ✓',
                data: [],
                borderColor: '#ff4976',
                backgroundColor: '#ff4976',
                pointStyle: 'triangle',
                pointRadius: 8,
                pointRotation: 180,
                showLine: false,
                order: 1
            },
            {
                label: 'Pattern DOWN ✗',
                data: [],
                borderColor: '#ff4976',
                backgroundColor: 'transparent',
                pointBorderWidth: 2,
                pointStyle: 'triangle',
                pointRadius: 8,
                pointRotation: 180,
                showLine: false,
                order: 1
            },
            // Random Strategy Trade Markers
            {
                label: 'Random UP ✓',
                data: [],
                borderColor: '#00d4aa',
                backgroundColor: '#00d4aa',
                pointStyle: 'circle',
                pointRadius: 6,
                showLine: false,
                order: 1
            },
            {
                label: 'Random UP ✗',
                data: [],
                borderColor: '#00d4aa',
                backgroundColor: 'transparent',
                pointBorderWidth: 2,
                pointStyle: 'circle',
                pointRadius: 6,
                showLine: false,
                order: 1
            },
            {
                label: 'Random DOWN ✓',
                data: [],
                borderColor: '#ff4976',
                backgroundColor: '#ff4976',
                pointStyle: 'circle',
                pointRadius: 6,
                showLine: false,
                order: 1
            },
            {
                label: 'Random DOWN ✗',
                data: [],
                borderColor: '#ff4976',
                backgroundColor: 'transparent',
                pointBorderWidth: 2,
                pointStyle: 'circle',
                pointRadius: 6,
                showLine: false,
                order: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index'
            },
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    enabled: true,
                    backgroundColor: 'rgba(30, 35, 48, 0.95)',
                    titleColor: '#a0a0a0',
                    bodyColor: '#ffffff',
                    borderColor: '#2d3748',
                    borderWidth: 1,
                    padding: 12,
                    displayColors: false,
                    callbacks: {
                        title: function(context) {
                            return context[0].label;
                        },
                        label: function(context) {
                            return '$' + context.parsed.y.toLocaleString('en-US', {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2
                            });
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        color: 'rgba(255, 255, 255, 0.05)',
                        borderColor: '#2d3748'
                    },
                    ticks: {
                        color: '#6c757d',
                        maxRotation: 0,
                        autoSkipPadding: 20
                    }
                },
                y: {
                    position: 'right',
                    grid: {
                        color: 'rgba(255, 255, 255, 0.05)',
                        borderColor: '#2d3748'
                    },
                    ticks: {
                        color: '#a0a0a0',
                        callback: function(value) {
                            return '$' + value.toLocaleString('en-US', {
                                minimumFractionDigits: 0,
                                maximumFractionDigits: 0
                            });
                        },
                        padding: 10
                    }
                }
            }
        }
    });
}

function updatePriceChart(history) {
    if (!priceChart || !history || history.length === 0) return;

    const labels = history.map(h => {
        const date = new Date(h.timestamp);
        return date.toLocaleTimeString('en-US', {hour: '2-digit', minute: '2-digit'});
    });

    const prices = history.map(h => h.end_price);

    priceChart.data.labels = labels;
    priceChart.data.datasets[0].data = prices;
    priceChart.update();

    // Load trade markers
    loadTradeMarkers();
}

function loadTradeMarkers() {
    // Load trades for both strategies
    Promise.all([
        fetch('/api/trades/pattern').then(r => r.json()),
        fetch('/api/trades/random').then(r => r.json())
    ])
    .then(([patternData, randomData]) => {
        const patternTrades = patternData.trades || [];
        const randomTrades = randomData.trades || [];

        updateTradeMarkers('pattern', patternTrades);
        updateTradeMarkers('random', randomTrades);

        priceChart.update();
    })
    .catch(error => console.error('Error loading trade markers:', error));
}

function updateTradeMarkers(strategyName, trades) {
    // Filter only completed trades with results
    const completedTrades = trades.filter(t => t.result && t.exit_price !== undefined);

    // Map trades to chart data points
    const chartLabels = priceChart.data.labels;
    const chartPrices = priceChart.data.datasets[0].data;

    // Determine dataset indices based on strategy
    const baseIndex = strategyName === 'pattern' ? 1 : 5; // Pattern starts at 1, Random at 5

    // Initialize arrays for each trade type
    const upCorrect = new Array(chartLabels.length).fill(null);
    const upIncorrect = new Array(chartLabels.length).fill(null);
    const downCorrect = new Array(chartLabels.length).fill(null);
    const downIncorrect = new Array(chartLabels.length).fill(null);

    completedTrades.forEach(trade => {
        // Find the chart index for this trade's timestamp
        const tradeDate = new Date(trade.timestamp);
        const tradeTime = tradeDate.toLocaleTimeString('en-US', {hour: '2-digit', minute: '2-digit'});

        const chartIndex = chartLabels.findIndex(label => label === tradeTime);

        if (chartIndex !== -1 && chartPrices[chartIndex] !== undefined) {
            const price = chartPrices[chartIndex];
            const direction = trade.direction;
            const correct = trade.result === 'win';

            // Place marker in appropriate array
            if (direction === 'UP' && correct) {
                upCorrect[chartIndex] = price;
            } else if (direction === 'UP' && !correct) {
                upIncorrect[chartIndex] = price;
            } else if (direction === 'DOWN' && correct) {
                downCorrect[chartIndex] = price;
            } else if (direction === 'DOWN' && !correct) {
                downIncorrect[chartIndex] = price;
            }
        }
    });

    // Update datasets
    priceChart.data.datasets[baseIndex].data = upCorrect;
    priceChart.data.datasets[baseIndex + 1].data = upIncorrect;
    priceChart.data.datasets[baseIndex + 2].data = downCorrect;
    priceChart.data.datasets[baseIndex + 3].data = downIncorrect;
}

// ═══════════════════════════════════════════════════════════════
// STRATEGIES DISPLAY
// ═══════════════════════════════════════════════════════════════

function updateStrategiesDisplay(strategies) {
    for (const [name, status] of Object.entries(strategies)) {
        updateStrategyCard(name, status);
    }
}

function updateStrategyCard(name, status) {
    const running = status.running;
    const position = status.current_position;
    const performance = status.performance;

    // Update toggle
    const toggle = document.getElementById(`${name}-toggle`);
    toggle.checked = running;

    // Update status badge
    const statusBadge = document.getElementById(`${name}-status`);
    statusBadge.textContent = running ? 'Running' : 'Stopped';
    statusBadge.className = `status-badge badge ${running ? 'bg-success' : 'bg-secondary'}`;

    // Update card styling
    const card = document.getElementById(`${name}-card`);
    if (running) {
        card.classList.add('running');
    } else {
        card.classList.remove('running');
    }

    // Update position
    const positionElement = document.getElementById(`${name}-position`);
    if (position) {
        positionElement.textContent = position;
        positionElement.className = `stat-value ${position.toLowerCase()}`;
    } else {
        positionElement.textContent = '-';
        positionElement.className = 'stat-value';
    }

    // Update Up/Down prices
    const upPriceElement = document.getElementById(`${name}-up-price`);
    if (status.up_price !== null && status.up_price !== undefined) {
        upPriceElement.textContent = status.up_price.toFixed(3);
    } else {
        upPriceElement.textContent = '-';
    }

    const downPriceElement = document.getElementById(`${name}-down-price`);
    if (status.down_price !== null && status.down_price !== undefined) {
        downPriceElement.textContent = status.down_price.toFixed(3);
    } else {
        downPriceElement.textContent = '-';
    }

    // Update balance
    const balanceElement = document.getElementById(`${name}-balance`);
    if (status.balance !== null && status.balance !== undefined) {
        balanceElement.textContent = `$${status.balance.toFixed(2)}`;
    } else {
        balanceElement.textContent = '$1000.00';
    }

    // Update P&L
    const pnlElement = document.getElementById(`${name}-pnl`);
    if (status.total_profit_loss !== null && status.total_profit_loss !== undefined) {
        const pnl = status.total_profit_loss;
        pnlElement.textContent = `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`;
        pnlElement.style.color = pnl >= 0 ? 'var(--color-up)' : 'var(--color-down)';
    } else {
        pnlElement.textContent = '$0.00';
        pnlElement.style.color = 'var(--text-primary)';
    }

    // Update win rate
    const winRateElement = document.getElementById(`${name}-win-rate`);
    if (performance && performance.final_win_rate !== undefined) {
        const wr = (performance.final_win_rate * 100).toFixed(1);
        winRateElement.textContent = `${wr}%`;
    } else {
        winRateElement.textContent = '--%';
    }

    // Update total predictions
    const totalElement = document.getElementById(`${name}-total`);
    totalElement.textContent = status.predictions_count || 0;

    // Update last 10
    const last10Element = document.getElementById(`${name}-last10`);
    if (performance && performance.last_10_final_wr !== undefined) {
        const wr = (performance.last_10_final_wr * 100).toFixed(1);
        last10Element.textContent = `${wr}%`;
    } else {
        last10Element.textContent = '--%';
    }
}

function updateStrategyStats(strategyName, stats, predictionsCount) {
    // Update win rate
    const winRateElement = document.getElementById(`${strategyName}-win-rate`);
    if (stats && stats.final_win_rate !== undefined) {
        const wr = (stats.final_win_rate * 100).toFixed(1);
        winRateElement.textContent = `${wr}%`;
    }

    // Update last 10
    const last10Element = document.getElementById(`${strategyName}-last10`);
    if (stats && stats.last_10_final_wr !== undefined) {
        const wr = (stats.last_10_final_wr * 100).toFixed(1);
        last10Element.textContent = `${wr}%`;
    }

    // Update total predictions if provided
    if (predictionsCount !== undefined) {
        const totalElement = document.getElementById(`${strategyName}-total`);
        totalElement.textContent = predictionsCount;
    }
}

// ═══════════════════════════════════════════════════════════════
// ACTIVITY FEED
// ═══════════════════════════════════════════════════════════════

function displayActivityFeed(items) {
    const feed = document.getElementById('activity-feed');
    feed.innerHTML = '';

    if (!items || items.length === 0) {
        feed.innerHTML = '<div class="text-muted text-center">No activity yet...</div>';
        return;
    }

    // Items are already in reverse chronological order from server
    // Just append them in order (don't insert at top during initial load)
    items.forEach(item => {
        addActivityItemToFeed(item, false); // false = append instead of prepend
    });
}


function addActivityItemToFeed(item, prepend = true) {
    const feed = document.getElementById('activity-feed');

    // Remove "no activity" message if present
    if (feed.querySelector('.text-muted')) {
        feed.innerHTML = '';
    }

    const div = document.createElement('div');
    div.className = `activity-item ${item.type}`;

    // Format timestamp in 24-hour format with date
    const date = new Date(item.timestamp);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const seconds = String(date.getSeconds()).padStart(2, '0');
    const time = `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;

    // Format message with strategy if present
    const message = item.strategy
        ? `<strong>${item.strategy.toUpperCase()}</strong>: ${item.message}`
        : item.message;

    div.innerHTML = `
        <div class="activity-time">${time}</div>
        <div class="activity-message">${message}</div>
    `;

    if (prepend) {
        // For new real-time items, add to top
        feed.insertBefore(div, feed.firstChild);
    } else {
        // For initial load, append to maintain server order (already newest-first)
        feed.appendChild(div);
    }

    // Keep only last 50 items visible
    while (feed.children.length > 50) {
        feed.removeChild(feed.lastChild);
    }
}

function addActivityItem(type, message) {
    // This function is kept for backward compatibility with socket events
    // It creates a temporary item that will be persisted by the server
    const item = {
        timestamp: new Date().toISOString(),
        type: type,
        message: message,
        strategy: null
    };
    addActivityItemToFeed(item);
}

function handleStrategyPrediction(data) {
    // Activity item is already saved by server, just add to feed
    const item = {
        timestamp: data.timestamp,
        type: 'info',
        message: `Predicted ${data.prediction} (Score: ${data.score >= 0 ? '+' : ''}${data.score})`,
        strategy: data.strategy
    };
    addActivityItemToFeed(item, true); // true = prepend to top

    // Update position in real-time
    const positionElement = document.getElementById(`${data.strategy}-position`);
    if (positionElement) {
        positionElement.textContent = data.prediction;
        positionElement.className = `stat-value ${data.prediction.toLowerCase()}`;
    }
}

function handleStrategyResult(data) {
    // Activity item is already saved by server, just add to feed
    const pred = data.prediction;
    const correct = pred.final_correct;
    const type = correct ? 'success' : 'danger';

    const item = {
        timestamp: data.timestamp,
        type: type,
        message: `${correct ? '✓' : '✗'} ${pred.actual_outcome} - Predicted ${pred.final_position} (${pred.price_change_pct >= 0 ? '+' : ''}${pred.price_change_pct.toFixed(2)}%)`,
        strategy: data.strategy
    };
    addActivityItemToFeed(item, true); // true = prepend to top

    // Update strategy stats in real-time
    if (data.stats) {
        updateStrategyStats(data.strategy, data.stats, data.predictions_count);
    }
}

function handleStrategyStatus(data) {
    // Activity item is already saved by server, just add to feed
    const item = {
        timestamp: new Date().toISOString(),
        type: 'info',
        message: data.status === 'started' ? 'Started' : 'Stopped',
        strategy: data.strategy
    };
    addActivityItemToFeed(item, true); // true = prepend to top
}

function handleMidPeriodCheck(data) {
    const strategyName = data.strategy;

    console.log(`[MID-PERIOD] ${strategyName.toUpperCase()} - Received prices:`, {
        up: data.up_price,
        down: data.down_price,
        reversed: data.reversed
    });

    // Update Up/Down prices (refreshed at midpoint regardless of reversal)
    if (data.up_price !== undefined && data.up_price !== null) {
        const upPriceElement = document.getElementById(`${strategyName}-up-price`);
        console.log(`[MID-PERIOD] Updating UP price element:`, upPriceElement ? 'FOUND' : 'NOT FOUND');
        if (upPriceElement) {
            upPriceElement.textContent = data.up_price.toFixed(3);
            console.log(`[MID-PERIOD] UP price updated to: ${data.up_price.toFixed(3)}`);
        }
    } else {
        console.warn(`[MID-PERIOD] UP price is undefined or null:`, data.up_price);
    }

    if (data.down_price !== undefined && data.down_price !== null) {
        const downPriceElement = document.getElementById(`${strategyName}-down-price`);
        console.log(`[MID-PERIOD] Updating DOWN price element:`, downPriceElement ? 'FOUND' : 'NOT FOUND');
        if (downPriceElement) {
            downPriceElement.textContent = data.down_price.toFixed(3);
            console.log(`[MID-PERIOD] DOWN price updated to: ${data.down_price.toFixed(3)}`);
        }
    } else {
        console.warn(`[MID-PERIOD] DOWN price is undefined or null:`, data.down_price);
    }

    // Activity item is already saved by server for both reversed and confirmed
    if (data.reversed) {
        const item = {
            timestamp: new Date().toISOString(),
            type: 'warning',
            message: `Mid-check: Position REVERSED to ${data.new_position}`,
            strategy: strategyName
        };
        addActivityItemToFeed(item, true); // true = prepend to top

        // Update position in real-time
        const positionElement = document.getElementById(`${strategyName}-position`);
        if (positionElement) {
            positionElement.textContent = data.new_position;
            positionElement.className = `stat-value ${data.new_position.toLowerCase()}`;
        }
    } else {
        // Position confirmed
        const item = {
            timestamp: new Date().toISOString(),
            type: 'info',
            message: `Mid-check: Position ${data.old_position} confirmed`,
            strategy: strategyName
        };
        addActivityItemToFeed(item, true); // true = prepend to top
    }
}

function handleBackfillComplete(data) {
    // Activity item is already saved by server, just add to feed
    const item = {
        timestamp: new Date().toISOString(),
        type: 'info',
        message: `Backfilled ${data.periods_added} historical periods from Binance`,
        strategy: data.strategy
    };
    addActivityItemToFeed(item, true); // true = prepend to top
}

function handleGapFilled(data) {
    // Activity item is already saved by server, just add to feed
    const item = {
        timestamp: new Date().toISOString(),
        type: 'info',
        message: `Filled ${data.gaps_filled} missing periods`,
        strategy: data.strategy || 'system'
    };
    addActivityItemToFeed(item, true); // true = prepend to top
}

function handleBetPlaced(data) {
    // Update strategy card with new prices and balance
    const strategyName = data.strategy;

    // Update prices
    if (data.up_price) {
        const upPriceElement = document.getElementById(`${strategyName}-up-price`);
        if (upPriceElement) upPriceElement.textContent = data.up_price.toFixed(3);
    }
    if (data.down_price) {
        const downPriceElement = document.getElementById(`${strategyName}-down-price`);
        if (downPriceElement) downPriceElement.textContent = data.down_price.toFixed(3);
    }

    // Update balance
    if (data.balance !== undefined) {
        const balanceElement = document.getElementById(`${strategyName}-balance`);
        if (balanceElement) balanceElement.textContent = `$${data.balance.toFixed(2)}`;
    }

    // Add activity item to feed
    const direction = data.direction;
    const amount = data.bet_amount;
    const price = data.entry_price;
    const potential = data.potential_profit;
    const midpoint = data.is_midpoint ? " (Midpoint)" : "";
    const message = `Bet placed${midpoint} - ${direction} - $${amount.toFixed(2)} at ${price.toFixed(3)} - Potential: $${potential >= 0 ? '+' : ''}${potential.toFixed(2)}`;

    const activityItem = {
        timestamp: data.timestamp || new Date().toISOString(),
        type: 'info',
        message: message,
        strategy: strategyName
    };

    addActivityItemToFeed(activityItem, true); // true = prepend to top
}

function handlePositionClosed(data) {
    // Update strategy card with new balance and P&L
    const strategyName = data.strategy;

    if (data.balance !== undefined) {
        const balanceElement = document.getElementById(`${strategyName}-balance`);
        if (balanceElement) balanceElement.textContent = `$${data.balance.toFixed(2)}`;
    }

    if (data.net_pnl !== undefined) {
        // Calculate total P&L (this is the net from this trade)
        // We'll refresh the full status to get accurate total P&L
        fetch('/api/strategies')
            .then(response => response.json())
            .then(strategies => {
                if (strategies[strategyName]) {
                    const status = strategies[strategyName];
                    const pnlElement = document.getElementById(`${strategyName}-pnl`);
                    if (pnlElement && status.total_profit_loss !== undefined) {
                        const pnl = status.total_profit_loss;
                        pnlElement.textContent = `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`;
                        pnlElement.style.color = pnl >= 0 ? 'var(--color-up)' : 'var(--color-down)';
                    }
                }
            })
            .catch(error => console.error('Error updating P&L:', error));
    }

    // Add activity item to feed
    const outcome = data.outcome;
    const pnl = data.net_pnl;
    const balance = data.balance;
    const message = `Trade closed - ${outcome} - P&L: $${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)} - Balance: $${balance.toFixed(2)}`;

    const activityItem = {
        timestamp: data.timestamp || new Date().toISOString(),
        type: pnl > 0 ? 'success' : 'danger',
        message: message,
        strategy: strategyName
    };

    addActivityItemToFeed(activityItem, true); // true = prepend to top

    // Reload trade markers to show the new trade on the chart
    loadTradeMarkers();
}

// ═══════════════════════════════════════════════════════════════
// STRATEGY CONTROLS
// ═══════════════════════════════════════════════════════════════

function setupEventListeners() {
    // Pattern strategy toggle
    document.getElementById('pattern-toggle').addEventListener('change', function() {
        toggleStrategy('pattern', this.checked);
    });

    // Random strategy toggle
    document.getElementById('random-toggle').addEventListener('change', function() {
        toggleStrategy('random', this.checked);
    });
}

function toggleStrategy(strategy, start) {
    const endpoint = start ? `/api/strategy/${strategy}/start` : `/api/strategy/${strategy}/stop`;

    fetch(endpoint, {method: 'POST'})
        .then(response => response.json())
        .then(data => {
            console.log(`Strategy ${strategy} ${start ? 'started' : 'stopped'}`, data);

            // Immediately fetch updated strategy status to update UI
            fetch('/api/strategies')
                .then(response => response.json())
                .then(strategies => {
                    updateStrategiesDisplay(strategies);
                })
                .catch(error => console.error('Error fetching strategy status:', error));
        })
        .catch(error => {
            console.error('Error toggling strategy:', error);
            // Revert toggle on error
            document.getElementById(`${strategy}-toggle`).checked = !start;
        });
}

// ═══════════════════════════════════════════════════════════════
// BACKTESTING
// ═══════════════════════════════════════════════════════════════

function setupBacktestListeners() {
    // Periods slider
    const periodsSlider = document.getElementById('backtest-periods');
    const periodsValue = document.getElementById('periods-value');
    const hoursEstimate = document.getElementById('hours-estimate');

    periodsSlider.addEventListener('input', function() {
        const periods = parseInt(this.value);
        periodsValue.textContent = periods;
        hoursEstimate.textContent = Math.round(periods * 5 / 60);
    });

    // Run backtest button
    document.getElementById('run-backtest-btn').addEventListener('click', runBacktest);
}

function runBacktest() {
    const strategy = document.getElementById('backtest-strategy').value;
    const periods = parseInt(document.getElementById('backtest-periods').value);

    // Disable button and show spinner
    const btn = document.getElementById('run-backtest-btn');
    const btnText = document.getElementById('backtest-btn-text');
    const spinner = document.getElementById('backtest-spinner');

    btn.disabled = true;
    btnText.textContent = 'Running...';
    spinner.classList.remove('d-none');

    // Show progress bar
    const progressContainer = document.getElementById('backtest-progress-container');
    progressContainer.classList.remove('d-none');
    updateProgressBar(0);

    // Clear previous results
    document.getElementById('backtest-results').innerHTML = '<div class="text-muted text-center">Running backtest...</div>';

    // Run backtest
    fetch('/api/backtest/run', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({strategy, periods})
    })
    .then(response => response.json())
    .then(data => {
        currentBacktestJob = data.job_id;
        console.log('Backtest started:', data);
    })
    .catch(error => {
        console.error('Error running backtest:', error);
        btn.disabled = false;
        btnText.textContent = 'Run Backtest';
        spinner.classList.add('d-none');
        progressContainer.classList.add('d-none');
        alert('Error running backtest: ' + error);
    });
}

function updateBacktestProgress(data) {
    if (data.job_id === currentBacktestJob) {
        updateProgressBar(data.progress);
    }
}

function updateProgressBar(progress) {
    const bar = document.getElementById('backtest-progress');
    bar.style.width = `${progress}%`;
    bar.textContent = `${progress}%`;
}

function handleBacktestComplete(data) {
    if (data.job_id === currentBacktestJob) {
        console.log('Backtest complete:', data);

        // Re-enable button
        const btn = document.getElementById('run-backtest-btn');
        const btnText = document.getElementById('backtest-btn-text');
        const spinner = document.getElementById('backtest-spinner');

        btn.disabled = false;
        btnText.textContent = 'Run Backtest';
        spinner.classList.add('d-none');

        // Hide progress bar after a moment
        setTimeout(() => {
            document.getElementById('backtest-progress-container').classList.add('d-none');
        }, 1000);

        // Display results
        displayBacktestResults(data.results);
    }
}

function displayBacktestResults(results) {
    const container = document.getElementById('backtest-results');

    if (results.comparison) {
        // Both strategies - show comparison
        container.innerHTML = renderComparisonResults(results);
    } else {
        // Single strategy
        container.innerHTML = renderSingleStrategyResults(results);
    }
}

function renderSingleStrategyResults(results) {
    const stats = results.stats;

    return `
        <div class="row">
            <div class="col-md-3 mb-3">
                <div class="result-card">
                    <div class="result-card-title">Total Predictions</div>
                    <div class="result-card-value">${stats.total_predictions}</div>
                </div>
            </div>
            <div class="col-md-3 mb-3">
                <div class="result-card">
                    <div class="result-card-title">Win Rate</div>
                    <div class="result-card-value ${stats.final_win_rate > 0.55 ? 'success' : stats.final_win_rate < 0.45 ? 'danger' : ''}">
                        ${(stats.final_win_rate * 100).toFixed(1)}%
                    </div>
                </div>
            </div>
            <div class="col-md-3 mb-3">
                <div class="result-card">
                    <div class="result-card-title">Reversal Impact</div>
                    <div class="result-card-value ${stats.reversal_improvement_pct > 0 ? 'success' : 'danger'}">
                        ${stats.reversal_improvement_pct >= 0 ? '+' : ''}${stats.reversal_improvement_pct.toFixed(1)}%
                    </div>
                </div>
            </div>
            <div class="col-md-3 mb-3">
                <div class="result-card">
                    <div class="result-card-title">Longest Win Streak</div>
                    <div class="result-card-value success">${stats.longest_win_streak}</div>
                </div>
            </div>
        </div>
        <div class="mt-3">
            <h6>Detailed Statistics</h6>
            <table class="table table-sm">
                <tr>
                    <td>Initial Win Rate:</td>
                    <td>${(stats.initial_win_rate * 100).toFixed(1)}%</td>
                </tr>
                <tr>
                    <td>Final Win Rate:</td>
                    <td>${(stats.final_win_rate * 100).toFixed(1)}%</td>
                </tr>
                <tr>
                    <td>Reversals Count:</td>
                    <td>${stats.reversals_count}</td>
                </tr>
                <tr>
                    <td>Longest Loss Streak:</td>
                    <td>${stats.longest_loss_streak}</td>
                </tr>
                ${stats.best_trade_pct ? `<tr><td>Best Trade:</td><td>${stats.best_trade_pct.toFixed(2)}%</td></tr>` : ''}
                ${stats.worst_trade_pct ? `<tr><td>Worst Trade:</td><td>${stats.worst_trade_pct.toFixed(2)}%</td></tr>` : ''}
            </table>
        </div>
    `;
}

function renderComparisonResults(results) {
    const patternStats = results.pattern.stats;
    const randomStats = results.random.stats;
    const comparison = results.comparison;

    return `
        <div class="row">
            <div class="col-12 mb-3">
                <div class="alert ${comparison.pattern_better ? 'alert-success' : 'alert-warning'}">
                    ${comparison.pattern_better ? '🎉' : '⚠️'}
                    <strong>${comparison.pattern_better ? 'Pattern strategy wins!' : 'Random strategy performs better'}</strong>
                    - ${Math.abs(comparison.difference * 100).toFixed(1)}% difference
                </div>
            </div>
        </div>
        <div class="row">
            <div class="col-md-6">
                <h6>Pattern Strategy</h6>
                <div class="result-card mb-3">
                    <div class="result-card-title">Win Rate</div>
                    <div class="result-card-value success">${(patternStats.final_win_rate * 100).toFixed(1)}%</div>
                </div>
                <table class="table table-sm">
                    <tr><td>Total Predictions:</td><td>${patternStats.total_predictions}</td></tr>
                    <tr><td>Initial WR:</td><td>${(patternStats.initial_win_rate * 100).toFixed(1)}%</td></tr>
                    <tr><td>Reversals:</td><td>${patternStats.reversals_count}</td></tr>
                    <tr><td>Longest Win Streak:</td><td>${patternStats.longest_win_streak}</td></tr>
                </table>
            </div>
            <div class="col-md-6">
                <h6>Random Strategy</h6>
                <div class="result-card mb-3">
                    <div class="result-card-title">Win Rate</div>
                    <div class="result-card-value">${(randomStats.final_win_rate * 100).toFixed(1)}%</div>
                </div>
                <table class="table table-sm">
                    <tr><td>Total Predictions:</td><td>${randomStats.total_predictions}</td></tr>
                    <tr><td>Initial WR:</td><td>${(randomStats.initial_win_rate * 100).toFixed(1)}%</td></tr>
                    <tr><td>Reversals:</td><td>${randomStats.reversals_count}</td></tr>
                    <tr><td>Longest Win Streak:</td><td>${randomStats.longest_win_streak}</td></tr>
                </table>
            </div>
        </div>
    `;
}

// ═══════════════════════════════════════════════════════════════
// TRADING CONFIGURATION
// ═══════════════════════════════════════════════════════════════

function initTradingConfig() {
    const updateConfigBtn = document.getElementById('update-config-btn');
    const resetTradingBtn = document.getElementById('reset-trading-btn');

    // Load current configuration from strategies
    fetch('/api/strategies')
        .then(response => response.json())
        .then(strategies => {
            // Get config from first strategy (they all share the same config)
            const firstStrategy = Object.values(strategies)[0];
            if (firstStrategy) {
                // Note: The trading engine's bet_amount and starting_capital are not exposed in get_status()
                // We'll use the defaults from the input fields, but users can change them
                console.log('Current strategy status:', firstStrategy);
            }
        })
        .catch(error => console.error('Error loading config:', error));

    // Update configuration
    updateConfigBtn.addEventListener('click', function() {
        const betAmount = parseFloat(document.getElementById('bet-amount').value);
        const startingCapital = parseFloat(document.getElementById('starting-capital').value);

        if (isNaN(betAmount) || betAmount < 1) {
            alert('Bet amount must be at least $1');
            return;
        }

        if (isNaN(startingCapital) || startingCapital < 100) {
            alert('Starting capital must be at least $100');
            return;
        }

        // Disable button during request
        updateConfigBtn.disabled = true;
        updateConfigBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Updating...';

        fetch('/api/trading/config', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                bet_amount: betAmount,
                starting_capital: startingCapital
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                alert('Configuration updated successfully!\n\nNew settings will apply to future trades.');

                // Refresh strategy status to show updated values
                fetch('/api/strategies')
                    .then(response => response.json())
                    .then(strategies => {
                        updateStrategiesDisplay(strategies);
                    });
            } else {
                alert('Error: ' + (data.error || 'Unknown error'));
            }
        })
        .catch(error => {
            console.error('Error updating config:', error);
            alert('Failed to update configuration: ' + error);
        })
        .finally(() => {
            // Re-enable button
            updateConfigBtn.disabled = false;
            updateConfigBtn.innerHTML = '<i class="bi bi-check-circle"></i> Update Configuration';
        });
    });

    // Reset trading
    resetTradingBtn.addEventListener('click', function() {
        if (!confirm('Are you sure you want to reset all balances and P/L?\n\nThis will:\n- Reset all balances to starting capital\n- Clear all P/L\n- Clear all trade history\n\nThis action cannot be undone.')) {
            return;
        }

        // Disable button during request
        resetTradingBtn.disabled = true;
        resetTradingBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Resetting...';

        fetch('/api/trading/reset', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                alert('All balances and P/L have been reset successfully!');

                // Refresh strategy status
                fetch('/api/strategies')
                    .then(response => response.json())
                    .then(strategies => {
                        updateStrategiesDisplay(strategies);
                    });
            } else {
                alert('Error: ' + (data.error || 'Unknown error'));
            }
        })
        .catch(error => {
            console.error('Error resetting trading:', error);
            alert('Failed to reset trading: ' + error);
        })
        .finally(() => {
            // Re-enable button
            resetTradingBtn.disabled = false;
            resetTradingBtn.innerHTML = '<i class="bi bi-arrow-counterclockwise"></i> Reset All Balances & P/L';
        });
    });
}
