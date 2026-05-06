"""
liga_engine.py
Algoritmo de generación de jornadas y cálculo de puntos.
Formato americano de pádel: 4 jugadores por cancha, 3 sets rotando pareja.

Sets por cancha:
  Set 1: P1+P2 vs P3+P4
  Set 2: P1+P3 vs P2+P4
  Set 3: P1+P4 vs P2+P3

Puntos de cada jugador = suma de diferencias de games en sus 3 sets.
"""
from __future__ import annotations


# ─────────────────────────────────────────────
# Cálculo de puntos
# ─────────────────────────────────────────────

def calcular_puntos_jugador(
    posicion: int,
    s1a: int, s1b: int,
    s2a: int, s2b: int,
    s3a: int, s3b: int,
) -> int:
    """
    Dado que 'a' es siempre el lado P1+Px y 'b' el lado contrario:
      P1: gana cuando 'a' gana en todos los sets
      P2: comparte Set1 con P1 (lado a), está en lado b en Set2 y Set3
      P3: está en lado b en Set1, lado a en Set2, lado b en Set3
      P4: está en lado b en Set1 y Set2, lado a en Set3
    """
    if posicion == 1:
        return (s1a - s1b) + (s2a - s2b) + (s3a - s3b)
    elif posicion == 2:
        return (s1a - s1b) + (s2b - s2a) + (s3b - s3a)
    elif posicion == 3:
        return (s1b - s1a) + (s2a - s2b) + (s3b - s3a)
    elif posicion == 4:
        return (s1b - s1a) + (s2b - s2a) + (s3a - s3b)
    return 0


def calcular_puntos_cancha(
    s1a: int, s1b: int,
    s2a: int, s2b: int,
    s3a: int, s3b: int,
) -> tuple[int, int, int, int]:
    """Devuelve (pts_P1, pts_P2, pts_P3, pts_P4)."""
    return (
        calcular_puntos_jugador(1, s1a, s1b, s2a, s2b, s3a, s3b),
        calcular_puntos_jugador(2, s1a, s1b, s2a, s2b, s3a, s3b),
        calcular_puntos_jugador(3, s1a, s1b, s2a, s2b, s3a, s3b),
        calcular_puntos_jugador(4, s1a, s1b, s2a, s2b, s3a, s3b),
    )


# ─────────────────────────────────────────────
# Generación de jornadas
# ─────────────────────────────────────────────

def generar_canchas(
    jugadores_activos: list[dict],
    num_canchas: int,
    ranking_previo: list[dict] | None = None,
) -> list[list[dict]]:
    """
    Asigna jugadores a canchas según su ranking acumulado.

    Args:
        jugadores_activos: lista de dicts con al menos 'id' y 'nombre'.
        num_canchas: número de canchas disponibles.
        ranking_previo: lista de dicts con 'id' y 'total_pts'.
                        Si es None o primera jornada, orden alfabético.

    Returns:
        Lista de canchas. Cada cancha es una lista de dicts de jugadores
        en posiciones 1-4 (posición = índice + 1).
    """
    # Construir mapa de puntos por jugador
    pts_map: dict[int, int] = {}
    if ranking_previo:
        for r in ranking_previo:
            pts_map[r["id"]] = r.get("total_pts", 0)

    # Ordenar: más puntos → mejor cancha (cancha 1 = la "alta")
    ordenados = sorted(
        jugadores_activos,
        key=lambda j: (-pts_map.get(j["id"], 0), j["nombre"]),
    )

    canchas: list[list[dict]] = []
    por_cancha = 4
    usados = 0

    for c in range(min(num_canchas, (len(ordenados) + 3) // 4)):
        grupo = ordenados[usados: usados + por_cancha]
        if grupo:
            canchas.append(grupo)
            usados += len(grupo)

    # Jugadores sobrantes: agregar uno por cancha empezando desde abajo
    sobrantes = ordenados[usados:]
    for i, jugador in enumerate(sobrantes):
        canchas[-(i + 1) % len(canchas)].append(jugador)

    return canchas


def guardar_jornada_en_db(
    torneo_id: int,
    canchas: list[list[dict]],
    horarios: list[str],
    fecha: str = "",
) -> int:
    """
    Persiste una nueva jornada y sus asignaciones en la DB.
    Retorna el id de la jornada creada.
    """
    from utils.database import (
        listar_jornadas,
        crear_jornada,
        crear_cancha_jornada,
        crear_asignacion,
    )

    jornadas_existentes = listar_jornadas(torneo_id)
    siguiente_numero = (max((j["numero"] for j in jornadas_existentes), default=0) + 1)

    jornada_id = crear_jornada(torneo_id, siguiente_numero, fecha)

    for i, grupo in enumerate(canchas):
        numero_cancha = i + 1
        horario = horarios[i] if i < len(horarios) else (horarios[-1] if horarios else "")
        cjid = crear_cancha_jornada(jornada_id, numero_cancha, horario)

        for posicion, jugador in enumerate(grupo, start=1):
            crear_asignacion(cjid, jugador["id"], posicion)

    return jornada_id


def rank_cancha(puntos_lista: list[int]) -> list[int]:
    """Dado [pts_P1, pts_P2, pts_P3, pts_P4], retorna posiciones 1-4."""
    indexed = sorted(enumerate(puntos_lista), key=lambda x: -x[1])
    ranks = [0] * len(puntos_lista)
    for rank, (idx, _) in enumerate(indexed, 1):
        ranks[idx] = rank
    return ranks


def generar_canchas_por_movimiento(
    canchas_previas: list[dict],
    jugadores_a_mover: int,
) -> list[list[dict]]:
    """
    Genera la siguiente jornada intercambiando jugadores entre canchas contiguas.

    Regla:
    - Si jugadores_a_mover = 1: sube 1 (mejor) y baja 1 (peor) por frontera de canchas.
    - Si jugadores_a_mover = 2: suben 2 (mejores) y bajan 2 (peores).

    Requiere canchas con 4 jugadores y resultado cargado en cada una.
    """
    if jugadores_a_mover not in (1, 2):
        raise ValueError("jugadores_a_mover debe ser 1 o 2")

    canchas_ordenadas = sorted(canchas_previas, key=lambda c: c["numero_cancha"])
    ranking_por_cancha: list[list[dict]] = []

    for cancha in canchas_ordenadas:
        jugadores = cancha.get("jugadores", [])
        resultado = cancha.get("resultado")
        if len(jugadores) != 4 or not resultado:
            raise ValueError("Cada cancha previa debe tener 4 jugadores y resultado cargado")

        pts = calcular_puntos_cancha(
            resultado["set1_a"], resultado["set1_b"],
            resultado["set2_a"], resultado["set2_b"],
            resultado["set3_a"], resultado["set3_b"],
        )

        jugadores_rank = []
        for idx, jug in enumerate(jugadores):
            jugadores_rank.append(
                {
                    "id": jug["jugador_id"],
                    "nombre": jug["nombre"],
                    "puntos": pts[idx],
                }
            )

        jugadores_rank.sort(key=lambda x: (-x["puntos"], x["nombre"]))
        ranking_por_cancha.append(jugadores_rank)

    siguiente: list[list[dict]] = []
    for i, cancha in enumerate(ranking_por_cancha):
        stay: list[dict] = []

        # Centro (si existe): estos no participan en intercambios.
        stay.extend(cancha[jugadores_a_mover: 4 - jugadores_a_mover])

        # Extremos bloqueados.
        if i == 0:
            # Cancha 1: los mejores no pueden subir mas, se quedan.
            stay.extend(cancha[:jugadores_a_mover])
        if i == len(ranking_por_cancha) - 1:
            # Ultima cancha: los peores no pueden bajar mas, se quedan.
            stay.extend(cancha[-jugadores_a_mover:])

        siguiente.append(stay)

    for i in range(len(ranking_por_cancha) - 1):
        suben_desde_abajo = ranking_por_cancha[i + 1][:jugadores_a_mover]
        bajan_desde_arriba = ranking_por_cancha[i][-jugadores_a_mover:]

        siguiente[i].extend(suben_desde_abajo)
        siguiente[i + 1].extend(bajan_desde_arriba)

    for cancha in siguiente:
        cancha.sort(key=lambda x: (-x["puntos"], x["nombre"]))
        if len(cancha) != 4:
            raise ValueError("La generacion por movimiento no produjo 4 jugadores por cancha")

    return [
        [{"id": j["id"], "nombre": j["nombre"]} for j in cancha]
        for cancha in siguiente
    ]
