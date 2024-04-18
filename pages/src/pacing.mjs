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
let target_power_data = [];
let prev_power_data = [];
let power_color_data = [];
let athlete_ftp;

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
    autoscroll: true,
    refreshInterval: 1,
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
    target_power_data = [];
    power_color_data = [];
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

// function get_target_power_array(distance, distance_arr, power_arr) {
//     let index = 0;
//     let min_diff = Math.abs(distance - distance_arr[0]);

//     for (let i = 1; i < distance_arr.length; i++) {
//         let difference = Math.abs(distance - distance_arr[i]);
//         if (difference < min_diff) {
//             min_diff = difference;
//             index = i;
//         }
//     }
//     return [power_arr.slice(index -50, index + 50), distance_arr.slice(index -50, index + 50)];
// }
function get_target_power_array(distance, distance_arr, power_arr) {
    let index = 0;
    if (distance >= distance_arr) {
        return null
    }
    for (let i = 0; i < distance_arr.length; i++) {
        if (distance_arr[i] >= distance) {
            index = i;
            break;
        }
    }
    let start = Math.max(0, index - 50);
    let end;
    if (distance_arr.slice(index, index + 50).length < 50) {
        end = distance_arr.length;
    } else {
        end = Math.min(distance_arr.length, index + 50);
    }
    

    return [power_arr.slice(start, end), distance_arr.slice(start, end)];
}

function getPowerColors(power, ftp, powerZones, powerColors) {
    let colors = [];
    for (let i = 0; i < power.length; i++) {
        let powerFtpRatio = power[i]/ftp;
        let currentZone = powerZones.find(zone => powerFtpRatio >= zone.from && (powerFtpRatio <= zone.to || zone.to === null));
        colors.push(powerColors[currentZone.zone])
    }
    return colors;
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
            console.log("Changed athlete ID!!!");
            athlete_distance = [];
            athlete_power = [];
            target_power_data = [];
            prev_power_data = [];
            power_color_data = [];
            athleteId = watching.athleteId;
            athlete_ftp = watching.athlete.ftp
            // common.rpc.getPowerZones(watching.state.power/watching.athlete.ftp).then(zones =>{ powerZones = zones; colors = common.getPowerZoneColors(powerZones)});
        }
        // console.log(watching.state)

        let target_power = Math.round(get_target_power(watching.state.distance, opt_results.distance, opt_results.power))
        document.getElementById('current_power').innerHTML = watching.state.power
        document.getElementById('target_power').innerHTML = target_power
        if (Math.abs(watching.state.power - target_power) <= 10) {
            document.getElementById('current_power').style.color = 'green';
        } else {
            document.getElementById('current_power').style.color = 'red';
        }
        athlete_power.push(watching.state.power);
        athlete_distance.push(watching.state.distance);
        let [target_power_arr, distance_arr] = get_target_power_array(watching.state.distance, opt_results.distance, opt_results.power);

        target_power_data = distance_arr.map((x, i) => [x, target_power_arr[i]]);
        prev_power_data = athlete_distance.slice(-100).map((x,i) => [x, athlete_power.slice(-100)[i]]);
        if (target_power_arr != null) {
            power_color_data = getPowerColors(target_power_arr, watching.athlete.ftp, powerZones, powerColors);
        }
        console.log("target power array lenth: ")
        console.log(target_power_arr[target_power_arr.length -1])
        console.log("prev power length")
        console.log(prev_power_data[0])
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
        
        
        let prev_power_series = {
            data: [[null, null], ...prev_power_data],
            type: 'line',
            smooth: true,
            showSymbol: false,
            lineStyle: {
                width: 2,
                color: 'black'
            }
        };
        series.push(prev_power_series);
        
        

        chart_options = {
            xAxis: {
                type: 'value',
                min: athlete_distance.slice(-100)[0],
                max: distance_arr[distance_arr.lenth - 1],
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
            series: series
        };
        chart.setOption(chart_options, true);
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