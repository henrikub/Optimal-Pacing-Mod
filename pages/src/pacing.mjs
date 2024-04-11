import * as sauce from '/pages/src/../../shared/sauce/index.mjs';
import * as common from '/pages/src/common.mjs';
import opt_result from './optimal_power.json' assert {type : 'json'};
const [echarts, theme] = await Promise.all([
    import('/pages/deps/src/echarts.mjs'),
    import('/pages/src/echarts-sauce-theme.mjs'),
]);
let opt_results = opt_result

const doc = document.documentElement;
const L = sauce.locale;
const H = L.human;
const num = H.number;
let imperial = common.storage.get('/imperialUnits');
L.setImperial(imperial);

let athleteId;
let athlete_power = [];
let athlete_distance = [];
let target_power_data = []
let prev_power_data = []

let gameConnection;

common.settingsStore.setDefault({
    autoscroll: true,
    refreshInterval: 2,
    overlayMode: false,
    fontScale: 1,
    solidBackground: false,
    backgroundColor: '#00ff00',
});


let overlayMode;
if (window.isElectron) {
    overlayMode = !!window.electron.context.spec.overlay;
    doc.classList.toggle('overlay-mode', overlayMode);
    document.querySelector('#titlebar').classList.toggle('always-visible', overlayMode !== true);
    if (common.settingsStore.get('overlayMode') !== overlayMode) {
        // Sync settings to our actual window state, not going to risk updating the window now
        common.settingsStore.set('overlayMode', overlayMode);
    }
}

function render() {

}

let cache = null;

async function check_json_change() {
  const response = await fetch('src/optimal_power.json');
  const data = await response.json();

  if (JSON.stringify(data) !== JSON.stringify(cache)) {
    console.log('The JSON file has changed');
    cache = data;
    opt_results = cache
    document.getElementById('message_box').innerHTML = 'Reoptimized!'
  } else {
    document.getElementById('message_box').innerHTML = ''
  }
}

setInterval(check_json_change, 5000);

function get_target_power(distance, distance_arr, power_arr) {
    let index = 0;
    let min_diff = Math.abs(distance - distance_arr[0]);

    for (let i = 1; i < distance_arr.length; i++) {
        let difference = Math.abs(distance - distance_arr[i]);
        if (difference < min_diff) {
            min_diff = difference;
            index = i;
        }
    }
    return power_arr[index];
}

function get_target_power_array(distance, distance_arr, power_arr) {
    let index = 0;
    let min_diff = Math.abs(distance - distance_arr[0]);

    for (let i = 1; i < distance_arr.length; i++) {
        let difference = Math.abs(distance - distance_arr[i]);
        if (difference < min_diff) {
            min_diff = difference;
            index = i;
        }
    }
    return [power_arr.slice(index, index + 50), distance_arr.slice(index, index + 50)];
}

export async function main() {
    common.initInteractionListeners();
    //common.initNationFlags();  // bg okay
  
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
            console.log("Changed athlete ID!!!")
            athlete_distance = []
            athlete_power = []
            target_power_data = []
            prev_power_data = []
            athleteId = watching.athleteId;
        }
        console.log(watching.state)
        let target_power = Math.round(get_target_power(watching.state.distance, opt_results.distance, opt_results.power))
        document.getElementById('current_power').innerHTML = watching.state.power
        document.getElementById('target_power').innerHTML = target_power
        if (Math.abs(watching.state.power - target_power) <= 10) {
            document.getElementById('current_power').style.color = 'green'
        } else {
            document.getElementById('current_power').style.color = 'red'
        }
        athlete_power.push(watching.state.power)
        athlete_distance.push(watching.state.distance)
        let [target_power_arr, distance_arr] = get_target_power_array(watching.state.distance, opt_results.distance, opt_results.power)

        target_power_data = distance_arr.map((x, i) => [x, target_power_arr[i]]);
        prev_power_data = athlete_distance.slice(-100).map((x,i) => [x, athlete_power.slice(-100)[i]]);

        chart_options = {
            xAxis: {
                type: 'value',
                min: 'dataMin',
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
            series: [
                {
                    data: target_power_data,
                    type: 'line',
                    showSymbol: false
                },
                {
                    data: prev_power_data,
                    type: 'line',
                    smooth: true,
                    showSymbol: false
                }
            ]
        };
        chart.setOption(chart_options);
    });
}

function setBackground() {
    const {solidBackground, backgroundColor} = common.settingsStore.get();
    doc.classList.toggle('solid-background', !!solidBackground);
    if (solidBackground) {
        doc.style.setProperty('--background-color', backgroundColor);
    } else {
        doc.style.removeProperty('--background-color');
    }
}


export async function settingsMain() {
    common.initInteractionListeners();
    await common.initSettingsForm('form#general')();
}