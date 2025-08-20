Param(
    [string]$CsvPath = ".\topics.csv"
)

$rows = Import-Csv $CsvPath -Delimiter ';'
foreach ($r in $rows) {
    $label = $r.label
    $mid = $r.mid
    docker compose run --rm gt-collector `
        python -u -m app.run_topic `
        --topic-mid $mid `
        --topic-label $label `
        --only-hourly --hourly-mode auto
    Start-Sleep -Seconds (Get-Random -Minimum 10 -Maximum 20)  # jitter anti-429
}
