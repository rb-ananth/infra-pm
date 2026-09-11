const RUPEES_PER_CRORE = 10_000_000n;
const PAISE_PER_RUPEE = 100n;
const PAISE_PER_CRORE = RUPEES_PER_CRORE * PAISE_PER_RUPEE;

function toScaledInteger(value: string, scale: number): bigint {
  const normalized = value.trim();
  if (!/^\d+(\.\d+)?$/.test(normalized)) {
    throw new Error("Invalid monetary value.");
  }

  const [whole, fraction = ""] = normalized.split(".");
  const paddedFraction = fraction.padEnd(scale + 1, "0");
  const retainedFraction = paddedFraction.slice(0, scale);
  let scaled = BigInt(`${whole}${retainedFraction}` || "0");

  if (paddedFraction[scale] >= "5") {
    scaled += 1n;
  }

  return scaled;
}

function formatScaledInteger(value: bigint, scale: number): string {
  const digits = value.toString().padStart(scale + 1, "0");
  const whole = digits.slice(0, -scale) || "0";
  const fraction = digits.slice(-scale);
  const groupedWhole = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");

  return `${groupedWhole}.${fraction}`;
}

/** Convert a user-entered crore value to an INR string for the API. */
export function croreToInr(value: string): string {
  const croreHundredths = toScaledInteger(value, 2);
  const paise = croreHundredths * (PAISE_PER_CRORE / 100n);
  return formatScaledInteger(paise, 2);
}

/** Format an INR API value as a readable crore value without floating point arithmetic. */
export function formatInrAsCrore(value: string): string {
  const paise = toScaledInteger(value, 2);
  const croreHundredths = (paise * 100n + PAISE_PER_CRORE / 2n) / PAISE_PER_CRORE;
  return formatScaledInteger(croreHundredths, 2);
}

/** Sum INR API values exactly and return the readable crore representation. */
export function sumInrAsCrore(values: string[]): string {
  const totalPaise = values.reduce(
    (total, value) => total + toScaledInteger(value, 2),
    0n,
  );
  const croreHundredths =
    (totalPaise * 100n + PAISE_PER_CRORE / 2n) / PAISE_PER_CRORE;
  return formatScaledInteger(croreHundredths, 2);
}