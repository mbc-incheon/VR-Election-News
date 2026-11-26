param([Parameter(Mandatory=$true)][string]$TextPath,[Parameter(Mandatory=$true)][string]$OutputPath,[ValidateSet(-2,0,2)][int]$Rate=0)
$ErrorActionPreference='Stop'
$articleText=Get-Content -LiteralPath $TextPath -Raw -Encoding UTF8
$articleVoice=New-Object -ComObject SAPI.SpVoice
$articleToken=New-Object -ComObject SAPI.SpObjectToken
$articleToken.SetId('HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices\Tokens\MSTTS_V110_koKR_HeamiM')
$articleVoice.Voice=$articleToken
$articleVoice.Rate=$Rate
$articleStream=New-Object -ComObject SAPI.SpFileStream
try {
 $articleStream.Open($OutputPath,3,$false)
 $articleVoice.AudioOutputStream=$articleStream
 $articleVoice.Speak($articleText,16) | Out-Null
} finally {$articleStream.Close()}
