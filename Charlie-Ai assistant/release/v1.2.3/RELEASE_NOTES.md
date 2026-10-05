# CHARLIE 1.2.3 / Build 107

Fixes restricted mouth opening on both photo avatars:

- Calibrate the actual lip seam and mouth width for each portrait.
- Increase jaw travel and map parted lip boundaries back to the original seam.
- Occlude the closed-mouth photograph inside the new mouth aperture.
- Stop multiplying an already audio-driven mouth shape by volume again.

Validation: closed, half-open and open renders inspected for both portraits;
15 avatar, articulation and Lifetime tests passed with the old app stopped.
This is a local executable update; no new downloadable installer was published.
