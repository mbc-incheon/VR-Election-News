# Generate Korean PCM WAV samples using the installed Windows Heami voice; no registry edits.
$ErrorActionPreference='Stop'
$sampleRoot=Join-Path $PSScriptRoot '../election-news-server/static/samples/narration'
$sampleRoot=(Resolve-Path -LiteralPath $sampleRoot).Path
$samples=Get-Content -LiteralPath (Join-Path $sampleRoot 'scripts.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$sampleVoice=New-Object -ComObject SAPI.SpVoice
$sampleToken=New-Object -ComObject SAPI.SpObjectToken
$sampleToken.SetId('HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices\Tokens\MSTTS_V110_koKR_HeamiM')
$sampleVoice.Voice=$sampleToken
$sampleVoice.Rate=-1
foreach ($sample in $samples.items) {
 $sampleStream=New-Object -ComObject SAPI.SpFileStream
 try {
  $sampleStream.Open((Join-Path $sampleRoot ($sample.id+'.wav')),3,$false)
  $sampleVoice.AudioOutputStream=$sampleStream
  $sampleVoice.Speak($sample.text) | Out-Null
 } finally {$sampleStream.Close()}
}
Write-Output 'Generated three Korean narration WAV files.'

& (Join-Path $PSScriptRoot '../.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'build_narration_catalog.py')
