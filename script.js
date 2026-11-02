const ESTATISTICAS = {
    "km": 31303.03,
    "empresas": 3,
    "psvs": 53,
    "campos": 25,
    "co2e": 170514.041528,
    "embarcacoes_com_emissoes": 49,
    "linhas_emissoes_invalidas": 0
};

document.getElementById("km").dataset.target = ESTATISTICAS.km;
document.getElementById("campos").dataset.target = ESTATISTICAS.campos;
document.getElementById("empresas").dataset.target = ESTATISTICAS.empresas;
document.getElementById("psvs").dataset.target = ESTATISTICAS.psvs;

const counters = document.querySelectorAll(".contador");

counters.forEach(counter => {

    const target = parseFloat(counter.dataset.target);

    let current = 0;

    const increment = Math.max(1, Math.ceil(target / 80));

    function update(){

        current += increment;

        if(current >= target){

            counter.innerText = Math.round(target).toLocaleString("pt-BR");

        }else{

            counter.innerText = Math.round(current).toLocaleString("pt-BR");

            requestAnimationFrame(update);

        }

    }

    update();

});


// CO2e indicator: precomputed by atualizar_home_page.py from the summary CSV.
function exibirTotalEmissoesCO2e() {
    const elementoValor = document.getElementById("co2e");
    const elementoCobertura = document.getElementById("co2e-cobertura");

    if (!elementoValor || !elementoCobertura) {
        console.warn("CO2e card not found in HTML.");
        return;
    }

    const totalToneladas = Number(ESTATISTICAS.co2e);
    const embarcacoesComDados = Number(ESTATISTICAS.embarcacoes_com_emissoes);

    if (!Number.isFinite(totalToneladas) || !Number.isFinite(embarcacoesComDados)) {
        elementoValor.textContent = "N/D";
        elementoCobertura.textContent = "Dados indisponiveis";
        console.error("Missing or invalid CO2e values in ESTATISTICAS.");
        return;
    }

    elementoValor.textContent = totalToneladas.toLocaleString("pt-BR", {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1
    });

    elementoCobertura.textContent =
        `${embarcacoesComDados} de ${ESTATISTICAS.psvs} embarcacoes com dados`;
    elementoCobertura.title =
        "Estimativa baseada no modelo de consumo e no fator de emissao da OFI; nao representa medicao direta de combustivel.";

    console.info("CO2e emissions indicator loaded:", {
        embarcacoesComDados,
        totalToneladasCO2e: totalToneladas
    });
}

exibirTotalEmissoesCO2e();
