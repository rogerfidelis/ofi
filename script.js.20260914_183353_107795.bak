const ESTATISTICAS = {
    km: 40714.42,
    empresas: 3,
    psvs: 53,
    campos: 35
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
