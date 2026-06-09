import { initializeApp } from "https://www.gstatic.com/firebasejs/10.8.1/firebase-app.js";
import { getFirestore, collection, getDocs } from "https://www.gstatic.com/firebasejs/10.8.1/firebase-firestore.js";

// =========================================================================
// ATENÇÃO: COLOQUE AQUI AS CONFIGURAÇÕES DO SEU PROJETO FIREBASE
// Vá no Console do Firebase -> Configurações do Projeto -> Seus aplicativos
// =========================================================================
const firebaseConfig = {
  apiKey: "AIzaSyDG4E_u9V8qFzrkDXVSV7-4JcuDjVO2CDw",
  authDomain: "inventario-sipac.firebaseapp.com",
  projectId: "inventario-sipac",
  storageBucket: "inventario-sipac.firebasestorage.app",
  messagingSenderId: "934802917713",
  appId: "1:934802917713:web:1359a45e0662cf5ee9ab70"
};

const app = initializeApp(firebaseConfig);
const db = getFirestore(app);

// Estado Global
let rawData = [];
let chartInstance = null;

// Filtros Selecionados
let selectedCodigo = null;
let selectedUnidade = null;
let selectedDenominacao = null;

// Elementos UI
const connStatus = document.getElementById('conn-status');
const kpiSomaSaldo = document.getElementById('kpi-soma-saldo');
const kpiUnidMedida = document.getElementById('kpi-unid-medida');

async function init() {
    connStatus.innerHTML = '<span class="material-icons-round sync-icon spinning">sync</span> Conectando...';
    try {
        if (firebaseConfig.apiKey === "SUA_API_KEY_AQUI") {
            // Mock Data for demonstration if Firebase is not configured
            rawData = generateMockData();
            console.warn("Aviso: Firebase não configurado. Exibindo dados de teste.");
            connStatus.innerHTML = '<span class="material-icons-round sync-icon">cloud_off</span> Modo Teste';
        } else {
            const querySnapshot = await getDocs(collection(db, "inventario"));
            rawData = [];
            querySnapshot.forEach((doc) => {
                rawData.push(doc.data());
            });
            connStatus.innerHTML = '<span class="material-icons-round sync-icon">cloud_done</span> Online';
            connStatus.classList.add('online');
        }
        
        setupSearchListeners();
        updateDashboard();

    } catch (error) {
        console.error("Erro Firebase:", error);
        connStatus.innerHTML = '<span class="material-icons-round sync-icon">error</span> Erro';
        connStatus.style.color = '#ef4444';
    }
}

function updateDashboard() {
    // 1. Filtrar os dados principais
    let filteredData = rawData;

    if (selectedCodigo) {
        filteredData = filteredData.filter(d => String(d['Código']) === String(selectedCodigo));
    }
    if (selectedUnidade) {
        filteredData = filteredData.filter(d => d['Unidade'] === selectedUnidade);
    }
    if (selectedDenominacao) {
        filteredData = filteredData.filter(d => d['Denominação'] === selectedDenominacao);
    }

    // 2. Atualizar KPIs
    updateKPIs(filteredData);

    // 3. Atualizar Gráfico
    updateChart(filteredData);

    // 4. Atualizar Listas (Comportamento do Power BI: Listas mostram as opções disponíveis com base nos outros filtros)
    renderFilterList('codigo', 'Código', selectedCodigo, (val) => { selectedCodigo = val; updateDashboard(); });
    renderFilterList('unidade', 'Unidade', selectedUnidade, (val) => { selectedUnidade = val; updateDashboard(); });
    renderFilterList('denominacao', 'Denominação', selectedDenominacao, (val) => { selectedDenominacao = val; updateDashboard(); });
}

function renderFilterList(type, fieldName, currentValue, onChangeCallback) {
    const listContainer = document.getElementById(`list-${type}`);
    const searchInput = document.getElementById(`search-${type}`).value.toLowerCase();
    
    // Obter valores únicos dos dados BRUTOS (para não sumir ao clicar), 
    // mas idealmente cruzar com os filtrados. Vamos usar os brutos para simplificar o "Clear filter"
    const uniqueValues = [...new Set(rawData.map(d => String(d[fieldName])))].sort();
    
    // Filtrar pela barra de pesquisa
    const searchFiltered = uniqueValues.filter(val => val.toLowerCase().includes(searchInput));

    listContainer.innerHTML = '';
    
    // Adicionar opção "Todos" (Limpar)
    if (currentValue) {
        const clearBtn = document.createElement('div');
        clearBtn.className = 'radio-item';
        clearBtn.style.color = '#0ea5e9';
        clearBtn.innerHTML = `
            <span class="material-icons-round" style="font-size:18px">clear</span>
            <span class="radio-label">Limpar Filtro</span>
        `;
        clearBtn.onclick = () => onChangeCallback(null);
        listContainer.appendChild(clearBtn);
    }

    searchFiltered.forEach((val) => {
        const div = document.createElement('div');
        div.className = 'radio-item';
        
        const isChecked = currentValue === val;
        
        div.innerHTML = `
            <input type="radio" name="radio-${type}" value="${val}" ${isChecked ? 'checked' : ''}>
            <span class="radio-label">${val}</span>
        `;
        
        div.onclick = (e) => {
            // Prevent double firing
            if(e.target.tagName !== 'INPUT') {
                const radio = div.querySelector('input');
                radio.checked = true;
            }
            onChangeCallback(val);
        };
        
        listContainer.appendChild(div);
    });
}

function setupSearchListeners() {
    ['codigo', 'unidade', 'denominacao'].forEach(type => {
        document.getElementById(`search-${type}`).addEventListener('input', () => {
            // Re-render apenas aquela lista
            const fieldMap = {
                'codigo': 'Código',
                'unidade': 'Unidade',
                'denominacao': 'Denominação'
            };
            
            let currentVal = null;
            let callback = null;
            if(type === 'codigo') { currentVal = selectedCodigo; callback = (v) => { selectedCodigo = v; updateDashboard(); }};
            if(type === 'unidade') { currentVal = selectedUnidade; callback = (v) => { selectedUnidade = v; updateDashboard(); }};
            if(type === 'denominacao') { currentVal = selectedDenominacao; callback = (v) => { selectedDenominacao = v; updateDashboard(); }};

            renderFilterList(type, fieldMap[type], currentVal, callback);
        });
    });
}

function formatMil(number) {
    if(number >= 1000000) return (number/1000000).toFixed(1).replace('.', ',') + ' Mi';
    if(number >= 1000) return (number/1000).toFixed(1).replace('.', ',') + ' Mil';
    return number.toString().replace('.', ',');
}

function updateKPIs(data) {
    let sumSaldo = 0;
    let firstMedida = '-';

    if (data.length > 0) {
        firstMedida = data[0]['Unid. Medida'] || '-';
        data.forEach(item => {
            sumSaldo += (parseFloat(item['Saldo']) || 0);
        });
    }

    kpiSomaSaldo.textContent = formatMil(sumSaldo);
    kpiUnidMedida.textContent = firstMedida.toUpperCase();
}

function updateChart(data) {
    // Agrupar Saldo por Unidade
    const unitTotals = {};
    data.forEach(item => {
        const un = item['Unidade'];
        unitTotals[un] = (unitTotals[un] || 0) + (parseFloat(item['Saldo']) || 0);
    });

    // Ordenar e pegar as maiores
    const sortedUnits = Object.entries(unitTotals)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 10);

    const labels = sortedUnits.map(u => {
        // Encurtar nome para o gráfico
        const name = u[0];
        return name.length > 25 ? name.substring(0, 25) + '...' : name;
    });
    
    const values = sortedUnits.map(u => u[1]);

    const ctx = document.getElementById('estoqueChart').getContext('2d');
    
    if (chartInstance) {
        chartInstance.destroy();
    }

    Chart.defaults.font.family = "'Outfit', sans-serif";
    Chart.defaults.color = '#64748b';

    chartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Soma de Saldo',
                data: values,
                backgroundColor: '#0ea5e9', // Azul
                borderRadius: 4,
                barPercentage: 0.6
            }]
        },
        options: {
            indexAxis: 'y', // Barra Horizontal
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return formatMil(context.raw);
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: '#e2e8f0' },
                    ticks: {
                        callback: function(value) {
                            return formatMil(value);
                        }
                    }
                },
                y: {
                    grid: { display: false }
                }
            }
        }
    });
}

// ==========================================
// MOCK DATA PARA DEMONSTRAÇÃO
// ==========================================
function generateMockData() {
    return [
        { "Código": "3022007000057", "Denominação": "ABACAXI, NATURAL, PÉROLA", "Unid. Medida": "UNIDADE", "Saldo": 8800, "Unidade": "ALMOXARIFADO CENTRAL DA SESAP" },
        { "Código": "3022007000057", "Denominação": "ABACAXI, NATURAL, PÉROLA", "Unid. Medida": "UNIDADE", "Saldo": 5600, "Unidade": "SUBSECRETARIA DE GESTÃO" },
        { "Código": "1002003000012", "Denominação": "ABÓBORA, JERIMUM, NATURAL", "Unid. Medida": "KG", "Saldo": 2900, "Unidade": "ALMOXARIFADO DO LACEN" },
        { "Código": "4005001000099", "Denominação": "ABRAÇADEIRA NÁILON", "Unid. Medida": "PCT", "Saldo": 1400, "Unidade": "ALMOXARIFADO DO CENTRO" },
        { "Código": "3022007000057", "Denominação": "ABACAXI, NATURAL, PÉROLA", "Unid. Medida": "UNIDADE", "Saldo": 1100, "Unidade": "ALMOXARIFADO REGIONAL" },
        { "Código": "1002003000012", "Denominação": "ABÓBORA, JERIMUM, NATURAL", "Unid. Medida": "KG", "Saldo": 1100, "Unidade": "HOSPITAL REGIONAL TARCÍSIO MAIA" },
        { "Código": "4005001000099", "Denominação": "ABRAÇADEIRA NÁILON", "Unid. Medida": "PCT", "Saldo": 1000, "Unidade": "HOSPITAL GISELDA TRIGUEIRO" },
    ];
}

init();
