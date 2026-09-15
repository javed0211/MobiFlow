// Gesture + business-logic helpers for ios_gesture_logic_lab
// GraalJS only — no Node APIs. Values live on `output`.

function toNumber(v, fallback) {
  var n = Number(v)
  return isFinite(n) ? n : (fallback == null ? 0 : fallback)
}

function round2(n) {
  return Math.round(n * 100) / 100
}

function cleanLabel(s) {
  return String(s == null ? '' : s)
    .replace(/\s+/g, ' ')
    .trim()
}

/** Cart math: subtotal → discount → tax → grand total */
function computeOrder(unitPrice, quantity, taxRate, discountPct) {
  var subtotal = round2(toNumber(unitPrice) * toNumber(quantity))
  var discount = round2(subtotal * toNumber(discountPct))
  var taxable = round2(subtotal - discount)
  var tax = round2(taxable * toNumber(taxRate))
  var total = round2(taxable + tax)
  return {
    subtotal: subtotal,
    discount: discount,
    taxable: taxable,
    tax: tax,
    total: total,
  }
}

function captureCopied() {
  try {
    if (typeof maestro !== 'undefined' && maestro.copiedText) {
      return String(maestro.copiedText)
    }
  } catch (e) {}
  return ''
}

function validateLabel(raw) {
  var label = cleanLabel(raw)
  output.copiedRaw = raw
  output.copiedLabel = label
  // Keep regex inside JS — Maestro ${} templates treat `$` as interpolation.
  if (!label) {
    output.labelOk = true
    return true
  }
  output.labelOk = /^[A-Za-z].{0,80}$/.test(label)
  return output.labelOk
}

function validateOrder(unitPrice, quantity, taxRate, discountPct, minTotal, currency) {
  var order = computeOrder(unitPrice, quantity, taxRate, discountPct)
  output.order = order
  output.meetsMinOrder = order.total >= toNumber(minTotal)
  output.taxNonNegative = order.tax >= 0
  output.discountLtSubtotal = order.discount < order.subtotal || order.subtotal === 0
  output.currencyOk = String(currency || '').length === 3
  output.orderOk =
    output.meetsMinOrder &&
    output.taxNonNegative &&
    output.discountLtSubtotal &&
    output.currencyOk
  return output.orderOk
}

output.logicLabReady = true
output.cleanLabel = cleanLabel
output.computeOrder = computeOrder
output.round2 = round2
output.toNumber = toNumber
output.captureCopied = captureCopied
output.validateLabel = validateLabel
output.validateOrder = validateOrder
