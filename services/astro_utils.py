import numpy as np

def calculate_extended_refraction(geom_alt_deg: float, temp_c: float, pressure_mbar: float) -> float:
    """
    Calculates atmospheric refraction with smooth cosine fade logic

    Range behavior:
      > 89.9°       : No refraction (near zenith, negligible effect).
      -3.0° to 89.9°: Full refraction (Bennett's formula).
      -3.0° to -5.0°: Smooth cosine damping from 100% to 0%.
      < -5.0°       : No refraction.
    """

    if geom_alt_deg > 89.9:
        return geom_alt_deg  # No refraction near zenith
    if geom_alt_deg < -5.0:
        return geom_alt_deg  # No refraction deep below horizon

    ARCMIN_TO_DEG = 1.0 / 60.0
    alt = geom_alt_deg

    # Iterate to converge apparent altitude
    for _ in range(10):
        prev_alt = alt

        # Clamp altitude to avoid division by zero
        safe_alt = np.clip(alt, -4.0, 89.9)

        argument = (safe_alt + 7.31 / (safe_alt + 4.4)) * np.deg2rad(1.0)

        base_refraction = ARCMIN_TO_DEG / np.tan(argument)

        # Weather correction
        refraction_val = base_refraction * (0.28 * pressure_mbar / (temp_c + 273.0))

        # Smooth fade below horizon (-3° to -5°) to prevent artifacts
        if alt > -3.0:
            factor = 1.0
        elif alt < -5.0:
            factor = 0.0
        else:
            # Smooth cosine interpolation: 1.0 at -3°, 0.0 at -5°
            t = (alt - (-5.0)) / 2.0
            factor = (1 - np.cos(t * np.pi)) / 2

        # Apply damping factor
        final_refraction = refraction_val * factor

        # Update altitude
        alt = geom_alt_deg + final_refraction

        # Check convergence
        if abs(alt - prev_alt) <= 3.0e-5:
            break

    return alt