// BTC Trading Dashboard JavaScript

// Global state
let socket = null;
let priceChart = null;
let lastPrice = null;
let currentBacktestJob = null;
let priceUpdateInterval = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    initializeSocket();
    initializePriceChart();
    loadInitialData();
    setupEventListeners();
    setupBacktestListeners();
    startPriceUpdates();
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
    const priceElement = document.getElementById('current-price');
    const changeElement = document.getElementById('price-change');

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
    priceChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'BTC Price',
                data: [],
                borderColor: 'rgb(75, 192, 192)',
                backgroundColor: 'rgba(75, 192, 192, 0.1)',
                tension: 0.1,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                y: {
                    ticks: {
                        callback: function(value) {
                            return '$' + value.toLocaleString();
                        }
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
}

// ═══════════════════════════════════════════════════════════════
// STRATEGIES DISPLAY
// ═══════════════════════════════════════════════════════════════

function updateStrategiesDisplay(strategies) {
    for (const [name, status] of Object.entries(strategies)) {
        updateStrategyCard(name, status);
    }
    updateComparison(strategies);
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

    // Update comparison section
    updateComparisonForStrategy(strategyName, stats, predictionsCount);
}

function updateComparison(strategies) {
    const pattern = strategies.pattern;
    const random = strategies.random;

    if (pattern && pattern.performance) {
        document.getElementById('comp-pattern-wr').textContent =
            (pattern.performance.final_win_rate * 100).toFixed(1) + '%';
        document.getElementById('comp-pattern-total').textContent =
            pattern.predictions_count;
    }

    if (random && random.performance) {
        document.getElementById('comp-random-wr').textContent =
            (random.performance.final_win_rate * 100).toFixed(1) + '%';
        document.getElementById('comp-random-total').textContent =
            random.predictions_count;
    }
}

function updateComparisonForStrategy(strategyName, stats, predictionsCount) {
    if (stats && stats.final_win_rate !== undefined) {
        const wrElement = document.getElementById(`comp-${strategyName}-wr`);
        if (wrElement) {
            wrElement.textContent = (stats.final_win_rate * 100).toFixed(1) + '%';
        }
    }

    if (predictionsCount !== undefined) {
        const totalElement = document.getElementById(`comp-${strategyName}-total`);
        if (totalElement) {
            totalElement.textContent = predictionsCount;
        }
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

    items.forEach(item => {
        addActivityItemToFeed(item);
    });
}

function addActivityItemToFeed(item) {
    const feed = document.getElementById('activity-feed');

    // Remove "no activity" message if present
    if (feed.querySelector('.text-muted')) {
        feed.innerHTML = '';
    }

    const div = document.createElement('div');
    div.className = `activity-item ${item.type}`;

    // Format timestamp
    const date = new Date(item.timestamp);
    const time = date.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });

    // Format message with strategy if present
    const message = item.strategy
        ? `<strong>${item.strategy.toUpperCase()}</strong>: ${item.message}`
        : item.message;

    div.innerHTML = `
        <div class="activity-time">${time}</div>
        <div class="activity-message">${message}</div>
    `;

    feed.insertBefore(div, feed.firstChild);

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
    addActivityItemToFeed(item);

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
    addActivityItemToFeed(item);

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
    addActivityItemToFeed(item);
}

function handleMidPeriodCheck(data) {
    // Activity item is already saved by server for both reversed and confirmed
    if (data.reversed) {
        const item = {
            timestamp: new Date().toISOString(),
            type: 'warning',
            message: `Mid-check: Position REVERSED to ${data.new_position}`,
            strategy: data.strategy
        };
        addActivityItemToFeed(item);

        // Update position in real-time
        const positionElement = document.getElementById(`${data.strategy}-position`);
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
            strategy: data.strategy
        };
        addActivityItemToFeed(item);
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
    addActivityItemToFeed(item);
}

function handleGapFilled(data) {
    // Activity item is already saved by server, just add to feed
    const item = {
        timestamp: new Date().toISOString(),
        type: 'info',
        message: `Filled ${data.gaps_filled} missing periods`,
        strategy: data.strategy || 'system'
    };
    addActivityItemToFeed(item);
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
