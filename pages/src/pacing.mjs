import * as sauce from '/pages/src/../../shared/sauce/index.mjs';
import * as common from '/pages/src/common.mjs';
import opt_results from './optimal_power.json' assert {type : 'json'};

const doc = document.documentElement;
const L = sauce.locale;
const H = L.human;
const num = H.number;
let imperial = common.storage.get('/imperialUnits');
L.setImperial(imperial);

// let targetPowerChart = new Chart(document.getElementById('target_power_chart'), {
//     type: 'line',
//     data: {
//         labels: Array(10).fill(''),
//         datasets: [{
//             label: 'Target Power',
//             data: targetPowerData,
//             fill: false,
//             borderColor: 'rgb(75, 192, 192)',
//             tension: 0.1
//         }]
//     }
// });

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
    // Må leggge til funksjonalitet for slutten av arrayet
    let index = 0;
    let min_diff = Math.abs(distance - distance_arr[0]);

    for (let i = 1; i < distance_arr.length; i++) {
        let difference = Math.abs(distance - distance_arr[i]);
        if (difference < min_diff) {
            min_diff = difference;
            index = i;
        }
    }
    return power_arr.slice(index, index + 100)
}

export async function main() {
    common.initInteractionListeners();
    //common.initNationFlags();  // bg okay
  

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

    common.storage.addEventListener('globalupdate', ev => {
        if (ev.data.key === '/imperialUnits') {
            L.setImperial(imperial = ev.data.value);
        } 
    });

    let athleteId;
    common.subscribe('athlete/watching', watching => {
        if (watching.athleteId !== athleteId) {
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

        let target_power_arr = get_target_power_array(watching.state.distance, opt_results.distance, opt_results.power)
        console.log(target_power_arr);


        // document.getElementById('w_bal').innerHTML = Math.round(watching.wBal)
        // document.getElementById('heart_rate').innerHTML = watching.state.heartrate
        // document.getElementById('distance').innerHTML = watching.state.distance
        // document.getElementById('speed').innerHTML = watching.state.speed
        // document.getElementById('time').innerHTML = watching.state.time
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
    //await initWindowsPanel();
}

