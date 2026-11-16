/**
 * Bilingual labels. English first, then Hiligaynon — the language spoken in Surallah
 * and across most of South Cotabato. Filipino is given where the Hiligaynon term is not
 * in common field use.
 *
 * These were written for this interface and should be checked by a first-language
 * speaker before field testing. Translation is not something to be confident about.
 */
export const L = {
  capture: { en: 'Take a photo', hil: 'Magkuha sing litrato' },
  myResults: { en: 'My results', hil: 'Akon mga resulta' },
  field: { en: 'Field', hil: 'Uma' },
  zone: { en: 'Zone', hil: 'Bahin sang uma' },
  note: { en: 'Note', hil: 'Nota' },
  send: { en: 'Send', hil: 'Ipadala' },
  what: { en: 'What was found', hil: 'Ano ang nakita' },
  where: { en: 'Where', hil: 'Diin' },
  howSevere: { en: 'How bad', hil: 'Ano kagrabe' },
  howConfident: { en: 'How sure the model is', hil: 'Kasiguro sang modelo' },
  whatToDo: { en: 'What to do', hil: 'Ano ang himuon' },
  whenToCall: { en: 'When to call a technician', hil: 'San-o magtawag sang technician' },
  queued: { en: 'Waiting to send', hil: 'Ginahulat ipadala' },
  synced: { en: 'Sent', hil: 'Napadala' },
  pendingReview: { en: 'Pending technician review', hil: 'Ginahulat ang technician' },
  isThisRight: { en: 'Is this right?', hil: 'Husto bala ini?' },
  photoTips: { en: 'For a usable photo', hil: 'Para sa maayo nga litrato' },
  gallery: { en: 'Choose a saved photo', hil: 'Pilia ang natago nga litrato' },
  yes: { en: 'Yes, that matches', hil: 'Huo, amo gid' },
  no: { en: 'No, not what I see', hil: 'Indi, lain ang akon nakita' },
  account: { en: 'My account', hil: 'Akon account' },
  changePassword: { en: 'Change password', hil: 'Ilisan ang password' },
  guideWelcome: { en: 'Welcome to AGRISCAN', hil: 'Maayong pag-abot sa AGRISCAN' },
  guideWaiting: { en: 'What happens next', hil: 'Ano ang masunod' },
  guideConfirm: { en: 'Tell us if it matches', hil: 'Sugiri kami kon husto' },
  guideOffline: { en: 'Works without signal', hil: 'Nagaobra bisan wala signal' },
  showGuide: { en: 'Show the guide again', hil: 'Ipakita liwat ang giya' },
}

export function Bi({ k, className }) {
  const label = L[k]
  if (!label) return null
  // The second language inherits its parent's colour at reduced opacity. Hardcoding
  // a grey here made it invisible on the coloured buttons: 1.03:1 on the Send button.
  return (
    <span className={className}>
      {label.en} <span className="bi-alt">· {label.hil}</span>
    </span>
  )
}
