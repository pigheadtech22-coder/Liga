from utils.data_manager import cargar_jornada, cargar_ranking_general, get_jornadas_disponibles
from utils.pdf_generator import generar_pdf_jornada, generar_pdf_ranking

print("Jornadas disponibles:", get_jornadas_disponibles())

canchas = cargar_jornada(2)
print(f"\nJornada 2 - {len(canchas)} canchas:")
for c in canchas:
    print(f"  Cancha {c['numero']}: sets={c['sets']}")
    for j in c['jugadores']:
        print(f"    {j['nombre'][:25]:25s}  pts={j['puntos']:+3d}  rank={j['rank_cancha']}")

ranking = cargar_ranking_general()
print(f"\nRanking General - {len(ranking)} jugadores:")
for r in ranking[:5]:
    print(f"  {r['posicion']}. {r['nombre'][:30]:30s}  total={r['total']:+3d}")

# Test PDF jornada
print("\nGenerando PDF de prueba (jornada 2)...")
generar_pdf_jornada(2, canchas, "test_jornada.pdf")
print("PDF jornada OK -> test_jornada.pdf")

# Test PDF ranking
print("Generando PDF de prueba (ranking)...")
generar_pdf_ranking(ranking, "test_ranking.pdf", jornada_ref=2)
print("PDF ranking OK -> test_ranking.pdf")
