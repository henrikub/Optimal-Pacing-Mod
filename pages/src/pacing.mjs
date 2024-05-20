import * as sauce from '/pages/src/../../shared/sauce/index.mjs';
import * as common from '/pages/src/common.mjs';
import opt_results_json from './optimal_power.json' assert {type : 'json'};

const [echarts, theme] = await Promise.all([
    import('/pages/deps/src/echarts.mjs'),
    import('/pages/src/echarts-sauce-theme.mjs'),
]);
let opt_results = opt_results_json

const doc = document.documentElement;
const L = sauce.locale;
const H = L.human;
const num = H.number;
let imperial = common.storage.get('/imperialUnits');
L.setImperial(imperial);

let lead_in = 0;
let athleteId;
let athlete_power = [];
let athlete_distance = [];
let target_power_data = [];
let prev_power_data = [];
let power_color_data = [];
let athlete_ftp;
let last_reopt = 0;
let reopt_count = 0;
let reoptimizing = false;

const powerZones = [
    {zone: 'Z1', from: 0, to: 0.5999},
    {zone: 'Z2', from: 0.6, to: 0.7599},
    {zone: 'Z3', from: 0.76, to: 0.8999},
    {zone: 'Z4', from: 0.90, to: 1.0499},
    {zone: 'Z5', from: 1.05, to: 1.1799},
    {zone: 'Z6', from: 1.18, to: null}
];
const powerColors = {
    Z1: '#8e8e86',
    Z2: '#0b6ff4',
    Z3: '#34bf34',
    Z4: '#e5e541',
    Z5: '#FF5F1F',
    Z6: '#e20404' 
};

let gameConnection;

common.settingsStore.setDefault({
    route: "Mech Isle Loop",
    cp: 250,
    w_prime: 20000,
    weight: 75,
    max_power: 700,
    num_laps: 1,
    integration_method: "RK4",
    negative_split: false,
    reoptimization: false,
    bound_start: 90,
    bound_end: 0,
    autoscroll: true,
    refreshInterval: 100,
    overlayMode: false,
    fontScale: 1,
    solidBackground: false,
    backgroundColor: '#00ff00',
    prevPowerColor: '#000000'
});

let settings = common.settingsStore.get();
setBackground();

let prev_power_series = {
    data: [[null, null]],
    type: 'line',
    smooth: true,
    showSymbol: false,
    lineStyle: {
        width: 2,
        color: settings.prevPowerColor
    }
};



let overlayMode;
if (window.isElectron) {
    overlayMode = !!window.electron.context.spec.overlay;
    doc.classList.toggle('overlay-mode', overlayMode);
    document.querySelector('#titlebar').classList.toggle('always-visible', overlayMode !== true);
    if (common.settingsStore.get('overlayMode') !== overlayMode) {
        common.settingsStore.set('overlayMode', overlayMode);
    }
}

function render() {

}

let cache = null;

async function check_json_change() {
    const response = await fetch('src/optimal_power.json');
    const data = await response.json();
    data.distance = data.distance.map(element => element + lead_in)

  if (JSON.stringify(data) !== JSON.stringify(cache)) {

    opt_results = data;
    // opt_results.distance = opt_results.distance.map(element => element + lead_in);
    cache = opt_results;
    document.getElementById('message_box').innerHTML = 'Reoptimized!';
    target_power_data = [];
    power_color_data = [];

  } else {
    document.getElementById('message_box').innerHTML = ''
  }
}

setInterval(check_json_change, 5000);

async function check_run_opt_button() {
    if (localStorage.getItem('optButtonClicked') === 'true') {
        console.log("opt button clicked")

        let opt_config = {
            route: settings.route,
            cp: settings.cp,
            w_prime: settings.w_prime,
            num_laps: settings.num_laps,
            weight: settings.weight,
            max_power: settings.max_power,
            integration_method: settings.integration_method,
            negative_split: settings.negative_split,
            bound_start: settings.bound_start,
            bound_end: settings.bound_end
        };
        fetch('http://localhost:5000/runopt', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(opt_config),
        })
        .then(response => response.json())
        .then(data => {
            console.log('Success:', data);
        })
        .catch((error) => {
            console.error('Error:', error);
        });
        localStorage.setItem('optButtonClicked', 'false');
    }
}

setInterval(check_run_opt_button, 3000)

function get_target_power(distance, distance_arr, power_arr) {
    let start = 0;
    let end = distance_arr.length - 1;

    while (start <= end) {
        let mid = Math.floor((start + end) / 2);
        if (distance_arr[mid] === distance) {
            return power_arr[mid];
        } else if (distance_arr[mid] < distance) {
            start = mid + 1;
        } else {
            end = mid - 1;
        }
    }

    if (start >= distance_arr.length) {
        return power_arr[end];
    } else if (end < 0) {
        return power_arr[start];
    } else {
        return Math.abs(distance - distance_arr[start]) < Math.abs(distance - distance_arr[end]) ? power_arr[start] : power_arr[end];
    }
}

function get_optimal_wbal(distance, distance_arr, w_bal_arr) {
    let start = 0;
    let end = distance_arr.length - 1;

    while (start <= end) {
        let mid = Math.floor((start + end) / 2);
        if (distance_arr[mid] === distance) {
            return w_bal_arr[mid];
        } else if (distance_arr[mid] < distance) {
            start = mid + 1;
        } else {
            end = mid - 1;
        }
    }

    if (start >= distance_arr.length) {
        start = distance_arr.length - 1;
    } 
    if (end < 0) {
        end = 0;
    }
    return Math.abs(distance - distance_arr[start]) < Math.abs(distance - distance_arr[end]) ? w_bal_arr[start] : w_bal_arr[end];
}


function get_target_power_array(distance, distance_arr, power_arr) {
    let start = 0;
    let end = distance_arr.length - 1;

    while (start <= end) {
        let mid = Math.floor((start + end) / 2);
        if (distance_arr[mid] === distance) {
            start = mid;
            break;
        } else if (distance_arr[mid] < distance) {
            start = mid + 1;
        } else {
            end = mid - 1;
        }
    }
    if (start >= distance_arr.length) {
        start = end;
    } else if (end < 0) {
        start = 0;
    }

    let sliceStart = Math.max(0, start - 50);
    let sliceEnd = Math.min(distance_arr.length, start + 50);
    return [power_arr.slice(sliceStart, sliceEnd), distance_arr.slice(sliceStart, sliceEnd)];
}

function getPowerColors(power, ftp, powerZones, powerColors) {
    let colors = [];
    for (let i = 0; i < power.length; i++) {
        let powerFtpRatio = power[i]/ftp;
        let closestZone = powerZones.reduce((prev, curr) => {
            return (Math.abs(curr.from - powerFtpRatio) < Math.abs(prev.from - powerFtpRatio) ? curr : prev);
        });
        colors.push(powerColors[closestZone.zone]);
    }
    return colors;
}


export async function main() {
    common.initInteractionListeners();
    window.addEventListener('resize', function() {
        chart.resize();
    });
    const gcs = await common.rpc.getGameConnectionStatus();

    gameConnection = !!(gcs && gcs.connected);
    doc.classList.toggle('game-connection', gameConnection);
    common.subscribe('status', gcs => {
        gameConnection = gcs.connected;
        doc.classList.toggle('game-connection', gameConnection);
    }, {source: 'gameConnection'});
    common.settingsStore.addEventListener('changed', async ev => {
        const changed = ev.data.changed;
        if (changed.has('solidBackground') || changed.has('backgroundColor')) {
            setBackground();
        }
        if (window.isElectron && changed.has('overlayMode')) {
            await common.rpc.updateWindow(window.electron.context.id,
                {overlay: changed.get('overlayMode')});
            await common.rpc.reopenWindow(window.electron.context.id);
        }
        render();
        
    });
    setBackground()
    common.storage.addEventListener('globalupdate', ev => {
        if (ev.data.key === '/imperialUnits') {
            L.setImperial(imperial = ev.data.value);
        } 
    });

    let chart = echarts.init(document.getElementById('chart_container'), 'sauce', {renderer: 'svg'});
    let chart_options;
    

    common.subscribe('athlete/watching', watching => {
        if (watching.athleteId !== athleteId) {
            console.log("Changed athlete ID!!!");
            athlete_distance = [];
            athlete_power = [];
            target_power_data = [];
            prev_power_data = [];
            power_color_data = [];
            athleteId = watching.athleteId;
            athlete_ftp = watching.athlete.ftp
            lead_in = 0;
        }
        // console.log(watching)
        settings = common.settingsStore.get()
        // console.log(settings.reoptimization)

        let target_power = Math.round(get_target_power(watching.state.distance, opt_results.distance, opt_results.power));
        let target_wbal = get_optimal_wbal(watching.state.distance, opt_results.distance, opt_results.w_bal);
        document.getElementById('current_power').innerHTML = watching.state.power;
        document.getElementById('target_power').innerHTML = target_power;
        document.getElementById('optimal_wbal').innerHTML = (Math.round(target_wbal) / 1000).toFixed(1);

        if (Math.abs(watching.state.power - target_power) <= 10) {
            document.getElementById('current_power').style.color = 'green';
        } else {
            document.getElementById('current_power').style.color = 'red';
        }
        athlete_power.push(watching.state.power);
        athlete_distance.push(watching.state.distance);

        let [target_power_arr, distance_arr] = get_target_power_array(watching.state.distance, opt_results.distance, opt_results.power);
        target_power_data = distance_arr.map((x, i) => [x, target_power_arr[i]]);
        
        if (prev_power_series.data.length >= 100) {
            prev_power_data.shift();
        }
        prev_power_data.push([watching.state.distance, watching.state.power]);

        prev_power_series.data = [[null, null], ...prev_power_data];
        if (target_power_arr != null && athlete_ftp !=null) {
            power_color_data = getPowerColors(target_power_arr, watching.athlete.ftp, powerZones, powerColors);
        }

        let series = [];
        if (target_power_arr != null && target_power_arr.length != 0) {
            let target_series = target_power_data.map((item, index) => {
                return {
                    data: [target_power_data[index - 1], item],
                    type: 'line',
                    showSymbol: false,
                    lineStyle: {
                        color: power_color_data[index]
                    },
                    areaStyle: {
                        color: power_color_data[index]
                    }
                };
            });
            target_series.push({
                data: [target_power_data[target_power_data.length - 1], null],
                type: 'line',
                showSymbol: false
            });
            series.push(...target_series);
        }

        chart_options = {
            animation: false,
            xAxis: {
                type: 'value',
                min: athlete_distance.slice(-100)[0],
                max: distance_arr[distance_arr.length - 1],
                name: 'Distance [m]',
                splitLine: {
                    show: false
                },
                axisLine: {
                    lineStyle: {
                        color: 'white'
                    }
                }
            },
            yAxis: {
                type: 'value',
                name: 'Power [W]',
                splitLine: {
                    show: false
                },
                axisLine: {
                    lineStyle: {
                        color: 'white'
                    }
                }
            },
        };        
        if (watching.state.distance === 0) {
            chart_options.series = [...series];
        } else if (watching.state.distance >= distance_arr[distance_arr.length - 1]) {
            chart_options.series = [];
        } else {
            chart_options.series = [...series, prev_power_series];
        }
        chart.setOption(chart_options, true);
        
        if (settings.reoptimization === true && watching.state.distance > 1000 && Math.abs(watching.wBal-target_wbal)>3000 && !reoptimizing && (watching.state.distance-last_reopt)>1000 && watching.state.distance < opt_results.distance[opt_results.distance.length-1] && watching.state.speed > 10) {
            console.log("Need to reoptimize!");
            reoptimizing = true;
            last_reopt = watching.state.distance
            reopt_count = reopt_count + 1;
            let opt_config = {
                route: settings.route,
                cp: settings.cp,
                w_prime: settings.w_prime,
                num_laps: settings.num_laps,
                weight: settings.weight,
                max_power: settings.max_power,
                integration_method: settings.integration_method,
                negative_split: settings.negative_split,
                bound_start: settings.bound_start,
                bound_end: settings.bound_end,
                distance: watching.state.distance - lead_in,
                speed: watching.state.speed/3.6,
                w_bal: watching.wBal,
                reopt_count: reopt_count
            };
            fetch('http://localhost:5000/reoptimalization', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(opt_config),
            })
            .then(response => response.json())
            .then(data => {
                console.log('Success:', data);
                if (data.result === 'Success') {
                    reoptimizing = false;
                }
            })
            .catch((error) => {
                console.error('Error:', error);
            });
    }    
    document.getElementById('startButton').addEventListener('click', function() {
    lead_in = athlete_distance[athlete_distance.length -1] + 5;
    opt_results.distance = opt_results.distance.map(element => element + lead_in);
    this.style.display = 'none';
    });
    
    });
}

function setBackground() {
    doc.classList.toggle('solid-background', !!settings.solidBackground);
    if (settings.solidBackground) {
        doc.style.setProperty('--background-color', settings.backgroundColor);
    } else {
        doc.style.removeProperty('--background-color');
    }
}

export async function settingsMain() {
    common.initInteractionListeners();
    await common.initSettingsForm('form')();
}