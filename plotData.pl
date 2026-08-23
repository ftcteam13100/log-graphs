#!/usr/bin/perl

use strict;
use Scalar::Util qw(looks_like_number);

my @xAxisData;
my @yAxisNames;
my @yAxisType; # 0: string array, 1: numerical, 2: fixed range
my @yAxisDataArrays;
my @yAxisDataMin;
my @yAxisDataMax;
my @yAxisDataUniqueValues;
my $startTime = 0;
my $endTime = 0;
my $numVisible = 2;
my $useUsec = 0;

my $idx;
my $xValue;
my $yValue;
my $valCount;

my @colors = ("orange", "green", "red", "blue", "brown", "purple", "palevioletred", "mediumvioletred", "darkolivegreen", "plum", "olive", "salmon", "slateblue", "gray");
my $numColors = scalar @colors;
my @sides = ("right", "left");
my $numSides = scalar @sides;

my %range = (
  "X" => [0, 144],
  "Y" => [0, 144],
  "ProjectedX" => [0, 144],
  "ProjectedY" => [0, 144],
  "shooterTarget" => [0, 2200],
  "shooterVelocity" => [0, 2200],
  "shooterAdjust" => [0, 2200],
);

sub timestamp2Num
{
    my $ts = $_[0];
    $ts =~ s/[:-\sTZ]//g;

    return $ts if(length($ts) < 14);

    my $yr = substr($ts, 0, 4);
    my $mon = substr($ts, 4, 2);
    my $day = substr($ts, 6, 2);
    my $hr = substr($ts, 8, 2);
    my $min = substr($ts, 10, 2);
    my $sec = substr($ts, 12, 2);

    my $t = 0;
    $t += 31 if($mon == 2);
    $t += 59 if($mon == 3);
    $t += 90 if($mon == 4);
    $t += 120 if($mon == 5);
    $t += 151 if($mon == 6);
    $t += 181 if($mon == 7);
    $t += 212 if($mon == 8);
    $t += 243 if($mon == 9);
    $t += 273 if($mon == 10);
    $t += 304 if($mon == 11);
    $t += 334 if($mon == 12);

    $t += ($day - 1);

    $t *= 24;
    $t += $hr;

    $t *= 60;
    $t += $min;

    $t *= 60;
    $t += $sec;

    return $t;
}

sub num2Timestamp
{
    my $ts = $_[0];
    return $ts if($ts < (30 * 60 * 10000)); # Timestamp is in millisec as data is less than 30 mins

    my $urlEscape = $_[1];

    my $sec = $ts % 60;
    $ts = int($ts/60);

    my $min = $ts % 60;
    $ts = int($ts/60);

    my $hr = $ts % 24;
    my $day = int($ts/24);

    my $mon = 0;
    if($day < 31) { $mon = 1; }
    elsif($day < 59) { $mon = 2; $day -= 31; }
    elsif($day < 90) { $mon = 3; $day -= 59; }
    elsif($day < 120) { $mon = 4; $day -= 90; }
    elsif($day < 151) { $mon = 5; $day -= 120; }
    elsif($day < 181) { $mon = 6; $day -= 151; }
    elsif($day < 212) { $mon = 7; $day -= 181; }
    elsif($day < 243) { $mon = 8; $day -= 212; }
    elsif($day < 273) { $mon = 9; $day -= 243; }
    elsif($day < 304) { $mon = 10; $day -= 273; }
    elsif($day < 334) { $mon = 11; $day -= 304; }
    elsif($day < 365) { $mon = 12; $day -= 334; }
    else { return "Invalid"; }

    $day += 1;
    my $yr = 2021;

    return sprintf("%04d-%02d-%02d %02d:%02d:%02d", $yr, $mon, $day, $hr, $min, $sec);
}

sub categoryCmpValues
{
    return $a <=> $b if(looks_like_number($a) && looks_like_number($b));

    if("${a}.${b}" =~ /^(\d+)\.(\d+)\.(\d+)\.(\d+)\.(\d+)\.(\d+)$/)
    {
        if($1 == $4)
        {
            if($2 == $5)
            {
                return $3 <=> $6;
            }
            else
            {
                return $2 <=> $5;
            }
        }
        else
        {
            return $1 <=> $4;
        }
    }
    else
    {
        return $a cmp $b;
    }
}

sub generateHTML
{
    my $outputFileName = $_[0];
    my $chartName = $outputFileName;
    $chartName =~ s/\.html$//;

    # Print HTML file output using plotly javascript
    open(OUTFILE, ">$outputFileName") or die "Cannot open $outputFileName for writing\n";

    print OUTFILE <<BEGIN_HTML;
<!DOCTYPE html>
<html>
<head>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <link rel="stylesheet" type="text/css" href="https://cdn.jsdelivr.net/bootstrap/3/css/bootstrap.css" />
    <style>
        .viewParameters {
            width: 98vw;
            height: 98vh;
        }
    </style>
</head>

<body>
        <div id="data_elem1" class="container-fluid"></div>
        <script>
            (function () {
BEGIN_HTML

    # Generate variable xvals
    print OUTFILE "\
                var xvals = [";
    foreach $xValue (@xAxisData)
    {
        if(!looks_like_number($xValue)){ print OUTFILE "\"$xValue\","; }
        else { print OUTFILE "$xValue,"; }
    }
    print OUTFILE "];\n";

    # Generate variable plotly_data
    print OUTFILE "\
                var plotly_data = [";
    foreach $idx (0..$#yAxisNames)
    {
        my $yIdx = $idx+1;
        print OUTFILE "\
                {\
                    name:\"$yAxisNames[$idx]\",\
                    type:\"line\",\
                    x:[],\
                    y:[";
        foreach $yValue (@{$yAxisDataArrays[$idx]})
        {
            if(!looks_like_number($yValue)) { print OUTFILE "\"$yValue\","; }
            else { print OUTFILE "$yValue,"; }

            if($yAxisType[$idx])
            {
                if(defined $range{$yAxisNames[$idx]})
		{
                    $yAxisDataMin[$idx] = $range{$yAxisNames[$idx]}[0];
                    $yAxisDataMax[$idx] = $range{$yAxisNames[$idx]}[1];
		    $yAxisType[$idx] = 2;
		}
		else
		{
                    $yAxisDataMin[$idx] = $yValue if($yAxisDataMin[$idx] eq "");
                    $yAxisDataMax[$idx] = $yValue if($yAxisDataMax[$idx] eq "");

                    $yAxisDataMin[$idx] = $yValue if($yAxisDataMin[$idx] > $yValue);
                    $yAxisDataMax[$idx] = $yValue if($yAxisDataMax[$idx] < $yValue);
		}
            }
        }
        print OUTFILE "],\
                    yaxis:\"y$yIdx\",\
                    line:\{color:\"$colors[$idx % $numColors]\"},";
        if($idx >= $numVisible)
        {
            print OUTFILE "\
                    visible:\"legendonly\",";
        }
        print OUTFILE "\
                },";
    }
    print OUTFILE "\
                ];\n";

    # Populate the x values for each emement of plotly_data
    print OUTFILE "\
                for(let i=0; i<plotly_data.length; i++)
                {
                    for(let j=0; j<xvals.length; j++)
                    {
                        plotly_data[i].x.push(xvals[j]);
                    }
                }\n";

    print OUTFILE "\
                var plotly_layout = {\
                    legend:{orientation:\"h\", x:0, y:1.02, yanchor:\"bottom\"},\
                    title:{text:\"$chartName\"},\
                    xaxis:{autorange:true,domain:[0.05,0.95],nticks:10,showgrid:true,tickcolor:\"#000\",tickfont:{size:7},ticklen:5,tickmode:\"auto\",tickwidth:0.5,type:\"category\",range:[-1,", $#xAxisData + 2, "]},";
    foreach $idx (0..$#yAxisNames)
    {
        my $axisName = "yaxis";
        $axisName .= ($idx + 1) if($idx > 0);
	my $autorange = "true";
	$autorange = "false" if($yAxisType[$idx] > 1);
        print OUTFILE "\
                    $axisName:{autorange:$autorange,";
        print OUTFILE "overlaying:\"y\"," if($idx > 0);
	my $position = ($idx % 2) ? 1 + 0.02 * $idx / 2 : 0 - 0.02 * $idx / 2;
        print OUTFILE "position:$position," if($idx > 1);
        print OUTFILE "side:\"$sides[$idx % $numSides]\",tickfont:\{color:\"$colors[$idx % $numColors]\"\},zeroline:false,";
        if($yAxisType[$idx] == 2)
        {
            my $minValue = $yAxisDataMin[$idx]; 
            my $maxValue = $yAxisDataMax[$idx];
            print OUTFILE "type:\"linear\",range:\[$minValue,$maxValue\],";
        }
        elsif($yAxisType[$idx] == 1)
        {
            my $minValue = $yAxisDataMin[$idx] - ($yAxisDataMax[$idx] - $yAxisDataMin[$idx]) * 0.05;
            my $maxValue = $yAxisDataMax[$idx] + ($yAxisDataMax[$idx] - $yAxisDataMin[$idx]) * 0.05;
            print OUTFILE "type:\"linear\",range:\[$minValue,$maxValue\],";
        }
        else
        {
            print OUTFILE "type:\"category\",categoryorder:\"array\",categoryarray:\[";
            $valCount = 0;
            my $prevVal;
            foreach my $val (sort categoryCmpValues (@{$yAxisDataArrays[$idx]}))
            {
                next if($val eq $prevVal);
                $prevVal = $val;

                if(!looks_like_number($val)) { print OUTFILE "\"$val\","; }
                else { print OUTFILE "$val,"; }
                $valCount++;
            }
            print OUTFILE "\],range:\[-1, $valCount\],";
        }
        print OUTFILE "visible:false," if($idx >= $numVisible);
        print OUTFILE "\},";
    }
    print OUTFILE "\
                };\n";

    print OUTFILE <<END_HTML;
                var currGraph = document.getElementById("data_elem1");
                Plotly.newPlot(currGraph, plotly_data, plotly_layout, {
                    queueLength: 7,
                    responsive: true
                });

                currGraph.on('plotly_legendclick', function(data) {
                   layout = data.layout

                   update_axis = 'yaxis'
                   if (data.curveNumber != 0) {
                      update_axis += data.curveNumber + 1;
                   }

                   shouldNotHideAxis = false;
                   if (
                     layout[update_axis].visible !== undefined
                     && layout[update_axis].visible == false
                   ) {
                      shouldNotHideAxis = true;
                   }

                   layout_updates = {};
                   layout_updates[update_axis + '.visible'] = shouldNotHideAxis;
                   Plotly.update(
                       document.getElementById('data_elem1'),
                       null, layout_updates
                   );
               });
            })()
        </script>
</body>
</html>
END_HTML

    close(OUTFILE);
}


if($#ARGV < 0 || $ARGV[0] eq "-h")
{
    print "Usage: $0 <opts> <param1> <param2> .... <inputFile>\n";
    print "\tInput file should be csv with 1st column as time and with header line.\n";
    print "\tParam names are exact match of the first word in the header names e.g., \"Tx_LO\" matches  \"Tx_LO\" and \"Tx_LO (GHz)\".\n";
    print "\tOptional Paramters\n";
    print "\t\t-u - Include usec from 2nd column in timestamp\n";
    print "\t\t-s:<start time and date> - E.g., 2021-08-18 10:21:43 or 20210818102143 etc. If Hr, Min or Sec is not specified, it is filled with 00\n";
    print "\t\t-e:<end   time and date> - E.g., 2021-08-18 10:21:43 or 20210818102143 etc. If Hr, Min or Sec is not specified, it is filled with 23 for hr, 59 for Min and 59 for sec\n";
    print "\t\t-n:<num> - Only first few paramters will be visible, and rest will be available to turn on\n";
    exit;
}


my $inputFile = pop @ARGV;
my $outputFile = $inputFile;
$outputFile =~ s/\.csv$//;
$outputFile =~ s/CSV\//HTML\//;

while($ARGV[0] =~ /^-([senu]):*(.*)/)
{
    my $opt = $1;
    my $val = $2;
    my $len;
    if($opt eq "s")
    {
        $val =~ s/[TZ\-\:\s]//g;
        $len = length($val);
        $val .= "000000" if($len == 8);
        $val .= "0000" if($len == 10);
        $val .= "00" if($len == 12);
        $startTime = &timestamp2Num($val);
        $outputFile .= "_s$val";
    }
    elsif($opt eq "e")
    {
        $val =~ s/[TZ\-\:\s]//g;
        $len = length($val);
        $val .= "235959" if($len == 8);
        $val .= "5959" if($len == 10);
        $val .= "59" if($len == 12);
        $endTime = &timestamp2Num($val);
        $outputFile .= "_e$val";
    }
    elsif($opt eq "n")
    {
       $numVisible = $val;
    }
    elsif($opt eq "u")
    {
        $useUsec = 1;
    }

    shift(@ARGV);
}
$outputFile .= ".html";

open(INFILE, $inputFile) or die "Cannot open $inputFile for reading\n";
my @statsFields;
my $line = <INFILE>;
$line =~ s/\s+$//;
my @headerNames = split(/\,\s*/, $line);
my @yAxisIdxs;

my @paramNames = @ARGV;
@paramNames = @headerNames if($#paramNames < 0);
$numVisible = $#paramNames+1 if($numVisible <= 0);

# Parse header line to find indexes of the parameters to be plotted
foreach my $paramName (@paramNames)
{
    foreach my $i (1..@headerNames)
    {
        if($headerNames[$i] =~ /^$paramName$/ || $headerNames[$i] =~ /^$paramName\s/)
        {
            push(@yAxisIdxs, $i);
            push(@yAxisNames, $headerNames[$i]);
            push(@yAxisType, 1); # Initialize as linear. While parsing data if any value is non-numerical, change it to category
            push(@yAxisDataMin, "");
            push(@yAxisDataMax, "");
            last;
        }
    }
}

# Parse each line and collect data to be plotted
my $prevTimeNum = 0;
my $curTimeNum;
while($line = <INFILE>)
{
    $line =~ s/\s+$//;
    @statsFields = split(/\,\s*/, $line);

    $curTimeNum = &timestamp2Num($statsFields[0]);

    next if($startTime && $curTimeNum < $startTime);
    last if($endTime && $curTimeNum > $endTime);
    next if($prevTimeNum && $curTimeNum <= $prevTimeNum);

#    if($prevTimeNum && $curTimeNum != $prevTimeNum+1)
#    {
#        foreach my $timeNum ($prevTimeNum+1 .. $curTimeNum-1)
#        {
#            my $timeStr = &num2Timestamp($timeNum);
#            $timeStr .= ".0" if($useUsec);
#            push @xAxisData, $timeStr;
#            foreach $idx (0..$#yAxisIdxs)
#            {
#                push @{$yAxisDataArrays[$idx]}, "";
#            }
#        }
#    }

    if($useUsec)
    {
        push @xAxisData, "$statsFields[0].$statsFields[1]";
    }
    else
    {
        push @xAxisData, $statsFields[0];
    }

    foreach $idx (0..$#yAxisIdxs)
    {
        push @{$yAxisDataArrays[$idx]}, $statsFields[$yAxisIdxs[$idx]];
        $yAxisType[$idx] = 0 if($yAxisType[$idx] && $statsFields[$yAxisIdxs[$idx]] ne "" && !looks_like_number($statsFields[$yAxisIdxs[$idx]]));
    }

    $prevTimeNum = $curTimeNum;
}
close(INFILE);

&generateHTML($outputFile);
