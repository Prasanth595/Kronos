# Paper trading Kronos 4h

Estado: activo como servicios de usuario, sin claves de exchange y sin capacidad
para enviar órdenes reales.

## Regla congelada

- Mercado: BTCUSDT, velas cerradas de 4 horas de Binance.
- Cuatro tendencias long-only: EMA 20/100, 20/200, 50/100 y 50/200.
- Cada componente usa 12,5 %; exposición máxima total 50 %, sin apalancamiento.
- Una entrada sólo se permite cuando la desviación entre tres predicciones Kronos
  no supera el percentil 90 de las últimas 1.080 observaciones.
- Cada componente sale con su cruce bajista.
- Se registra simultáneamente un control con las mismas tendencias y costes pero
  sin filtro Kronos, para medir el aporte incremental real de la IA.
- Simulación incluye 0,10 % de comisión y 0,02 % de slippage por lado.
- Corte diario: 4 %. Parada definitiva del experimento: drawdown del 20 %.

## Consultar

```bash
cd /home/ocultwolf/newBot/kronos
kronos_env/bin/python Kronos/examples/paper_status.py
systemctl --user status kronos-api.service kronos-paper-trader.service
journalctl --user -u kronos-paper-trader.service -n 30 --no-pager
kronos_env/bin/python Kronos/examples/audit_paper_journal.py
```

Datos persistentes:

- `outputs/paper_kronos_trend_4h/state.json`
- `outputs/paper_kronos_trend_4h/journal.csv`
- `outputs/paper_kronos_trend_4h/audit.json`
- `outputs/kronos_research_4h_3y/paper_candidate_validation/report.json`

## Puerta antes de dinero real

No se considerará conexión a un exchange hasta cumplir simultáneamente:

1. mínimo 90 días de ejecución forward sin cambiar la regla;
2. al menos dos ciclos completos de entrada y salida;
3. rentabilidad neta positiva y drawdown no superior al 10 % en paper;
4. ninguna vela perdida o duplicada y servicios estables;
5. nueva revisión humana explícita de resultados, límites y tamaño inicial.

Incluso superando estos puntos no existe garantía de beneficio. El primer capital,
si se autoriza posteriormente, deberá ser pequeño y no necesario para gastos.
