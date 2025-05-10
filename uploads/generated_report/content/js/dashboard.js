/*
   Licensed to the Apache Software Foundation (ASF) under one or more
   contributor license agreements.  See the NOTICE file distributed with
   this work for additional information regarding copyright ownership.
   The ASF licenses this file to You under the Apache License, Version 2.0
   (the "License"); you may not use this file except in compliance with
   the License.  You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
*/
var showControllersOnly = false;
var seriesFilter = "";
var filtersOnlySampleSeries = true;

/*
 * Add header in statistics table to group metrics by category
 * format
 *
 */
function summaryTableHeader(header) {
    var newRow = header.insertRow(-1);
    newRow.className = "tablesorter-no-sort";
    var cell = document.createElement('th');
    cell.setAttribute("data-sorter", false);
    cell.colSpan = 1;
    cell.innerHTML = "Requests";
    newRow.appendChild(cell);

    cell = document.createElement('th');
    cell.setAttribute("data-sorter", false);
    cell.colSpan = 3;
    cell.innerHTML = "Executions";
    newRow.appendChild(cell);

    cell = document.createElement('th');
    cell.setAttribute("data-sorter", false);
    cell.colSpan = 7;
    cell.innerHTML = "Response Times (ms)";
    newRow.appendChild(cell);

    cell = document.createElement('th');
    cell.setAttribute("data-sorter", false);
    cell.colSpan = 1;
    cell.innerHTML = "Throughput";
    newRow.appendChild(cell);

    cell = document.createElement('th');
    cell.setAttribute("data-sorter", false);
    cell.colSpan = 2;
    cell.innerHTML = "Network (KB/sec)";
    newRow.appendChild(cell);
}

/*
 * Populates the table identified by id parameter with the specified data and
 * format
 *
 */
function createTable(table, info, formatter, defaultSorts, seriesIndex, headerCreator) {
    var tableRef = table[0];

    // Create header and populate it with data.titles array
    var header = tableRef.createTHead();

    // Call callback is available
    if(headerCreator) {
        headerCreator(header);
    }

    var newRow = header.insertRow(-1);
    for (var index = 0; index < info.titles.length; index++) {
        var cell = document.createElement('th');
        cell.innerHTML = info.titles[index];
        newRow.appendChild(cell);
    }

    var tBody;

    // Create overall body if defined
    if(info.overall){
        tBody = document.createElement('tbody');
        tBody.className = "tablesorter-no-sort";
        tableRef.appendChild(tBody);
        var newRow = tBody.insertRow(-1);
        var data = info.overall.data;
        for(var index=0;index < data.length; index++){
            var cell = newRow.insertCell(-1);
            cell.innerHTML = formatter ? formatter(index, data[index]): data[index];
        }
    }

    // Create regular body
    tBody = document.createElement('tbody');
    tableRef.appendChild(tBody);

    var regexp;
    if(seriesFilter) {
        regexp = new RegExp(seriesFilter, 'i');
    }
    // Populate body with data.items array
    for(var index=0; index < info.items.length; index++){
        var item = info.items[index];
        if((!regexp || filtersOnlySampleSeries && !info.supportsControllersDiscrimination || regexp.test(item.data[seriesIndex]))
                &&
                (!showControllersOnly || !info.supportsControllersDiscrimination || item.isController)){
            if(item.data.length > 0) {
                var newRow = tBody.insertRow(-1);
                for(var col=0; col < item.data.length; col++){
                    var cell = newRow.insertCell(-1);
                    cell.innerHTML = formatter ? formatter(col, item.data[col]) : item.data[col];
                }
            }
        }
    }

    // Add support of columns sort
    table.tablesorter({sortList : defaultSorts});
}

$(document).ready(function() {

    // Customize table sorter default options
    $.extend( $.tablesorter.defaults, {
        theme: 'blue',
        cssInfoBlock: "tablesorter-no-sort",
        widthFixed: true,
        widgets: ['zebra']
    });

    var data = {"OkPercent": 100.0, "KoPercent": 0.0};
    var dataset = [
        {
            "label" : "FAIL",
            "data" : data.KoPercent,
            "color" : "#FF6347"
        },
        {
            "label" : "PASS",
            "data" : data.OkPercent,
            "color" : "#9ACD32"
        }];
    $.plot($("#flot-requests-summary"), dataset, {
        series : {
            pie : {
                show : true,
                radius : 1,
                label : {
                    show : true,
                    radius : 3 / 4,
                    formatter : function(label, series) {
                        return '<div style="font-size:8pt;text-align:center;padding:2px;color:white;">'
                            + label
                            + '<br/>'
                            + Math.round10(series.percent, -2)
                            + '%</div>';
                    },
                    background : {
                        opacity : 0.5,
                        color : '#000'
                    }
                }
            }
        },
        legend : {
            show : true
        }
    });

    
    createTable($("#statisticsTable"), {"supportsControllersDiscrimination": true, "overall": {"data": ["Total", 494, 0, 0.0, 912.7955465587045, 5, 7616, 195.0, 6893.5, 7223.0, 7575.1, 0.8245412863177889, 47.242436080316, 1.0402267316410208], "isController": false}, "titles": ["Label", "#Samples", "FAIL", "Error %", "Average", "Min", "Max", "Median", "90th pct", "95th pct", "99th pct", "Transactions/s", "Received", "Sent"], "items": [{"data": ["029_POST_web/emazad/Biddings/EnterMazadForMazadUserAsync", 12, 0, 0.0, 434.75, 327, 462, 443.5, 461.4, 462.0, 462.0, 0.022405030676221165, 0.00940836249099131, 0.03763344996396524], "isController": false}, {"data": ["028_POST_web/emazad/GetAuctionsByCauseId/List", 12, 0, 0.0, 126.83333333333334, 121, 146, 125.0, 140.9, 146.0, 146.0, 0.022417712982284402, 0.030747732308221132, 0.014536485761950041], "isController": false}, {"data": ["021_GET_web/emazad/AuctionBidderStatsus/GetAsync", 12, 0, 0.0, 189.08333333333334, 183, 199, 187.5, 198.1, 199.0, 199.0, 0.022421901713593838, 0.01020371699075657, 0.035953869739961994], "isController": false}, {"data": ["011_POST_web/emazad/GetCausesOrAuctionsBySearch/Execute", 12, 0, 0.0, 7286.166666666667, 7042, 7616, 7223.0, 7603.7, 7616.0, 7616.0, 0.022101482641127174, 0.27024854095681, 0.04118127820241274], "isController": false}, {"data": ["018_GET_web/emazad/GetAuctionDetailsForPublic/Execute", 12, 0, 0.0, 318.8333333333333, 274, 366, 320.5, 354.30000000000007, 366.0, 366.0, 0.022417503586800575, 0.05027519237020265, 0.03695385356886657], "isController": false}, {"data": ["013_POST_web/emazad/GetCausesOrAuctionsBySearch/Execute", 12, 0, 0.0, 7269.916666666666, 7036, 7533, 7228.0, 7528.8, 7533.0, 7533.0, 0.02212075350660028, 0.2704895783600042, 0.04121718524472005], "isController": false}, {"data": ["017_POST_web/emazad/GetAuctionsByCauseId/List", 12, 0, 0.0, 201.74999999999997, 194, 214, 199.5, 214.0, 214.0, 214.0, 0.022421357090006803, 0.12282480722304019, 0.039281166620578324], "isController": false}, {"data": ["004_POST_web/emazad/GetCausesOrAuctionsBySearch/Execute", 13, 0, 0.0, 7271.076923076924, 6898, 7613, 7173.0, 7601.4, 7613.0, 7613.0, 0.021971038790714027, 0.268656686463136, 0.016671383926157027], "isController": false}, {"data": ["007_GET_captcha", 13, 0, 0.0, 104.23076923076923, 50, 445, 65.0, 327.39999999999986, 445.0, 445.0, 0.022268510270922123, 0.29888181566298494, 0.00948151413879106], "isController": false}, {"data": ["006_POST_web/emazad/GetCausesOrAuctionsBySearch/Execute", 13, 0, 0.0, 7194.615384615385, 6889, 7506, 7143.0, 7476.0, 7506.0, 7506.0, 0.021992485336933335, 0.26892223393745, 0.016687657330856642], "isController": false}, {"data": ["005_POST_web/emazad/GetCausesOrAuctionsBySearch/Count", 13, 0, 0.0, 123.92307692307692, 102, 184, 118.0, 172.0, 184.0, 184.0, 0.0222535674180384, 0.011713547693674508, 0.016842299559550546], "isController": false}, {"data": ["025_POST_web/emazad/Bill/GetMyBills", 12, 0, 0.0, 417.4999999999999, 255, 1921, 270.5, 1447.6000000000017, 1921.0, 1921.0, 0.022400011946673036, 1.2786290673521692, 0.03952814608167791], "isController": false}, {"data": ["008_POST_web/emazad/Account/Login", 12, 0, 0.0, 411.3333333333333, 397, 434, 410.0, 431.90000000000003, 434.0, 434.0, 0.022378540471590443, 0.025416252508261412, 0.015275976357071994], "isController": false}, {"data": ["016_POST_web/emazad/GetAuctionsByCauseId/Counter", 12, 0, 0.0, 175.75, 166, 194, 173.5, 192.5, 194.0, 194.0, 0.02242148277002472, 0.011714348908167211, 0.03934707474388127], "isController": false}, {"data": ["030_GET_web/emazad/Biddings/GetAuctionSubscriptionStatus", 12, 0, 0.0, 204.08333333333331, 195, 223, 204.0, 218.8, 223.0, 223.0, 0.02241093055786409, 0.009870439142184282, 0.03611136271530835], "isController": false}, {"data": ["001_GET_-6", 13, 0, 0.0, 77.6923076923077, 75, 82, 77.0, 82.0, 82.0, 82.0, 0.022237655535294578, 15.459318440982116, 0.013029876290211666], "isController": false}, {"data": ["001_GET_-5", 13, 0, 0.0, 9.23076923076923, 8, 10, 9.0, 10.0, 10.0, 10.0, 0.02224028056969334, 0.5504903821478979, 0.013096571468286217], "isController": false}, {"data": ["001_GET_-4", 13, 0, 0.0, 10.461538461538462, 10, 12, 10.0, 11.6, 12.0, 12.0, 0.022240204473018353, 0.7435699612678285, 0.013139964556812602], "isController": false}, {"data": ["001_GET_-3", 13, 0, 0.0, 6.538461538461538, 6, 7, 7.0, 7.0, 7.0, 7.0, 0.02224035666688907, 0.07619059686274107, 0.01309661627942784], "isController": false}, {"data": ["031_GET_web/emazad/GetLastFiveBiddings/GetAsync", 12, 0, 0.0, 254.50000000000003, 239, 282, 252.5, 277.8, 282.0, 282.0, 0.02240913097390083, 0.03666832653745313, 0.03680874833798945], "isController": false}, {"data": ["001_GET_-2", 13, 0, 0.0, 27.692307692307693, 26, 29, 28.0, 29.0, 29.0, 29.0, 0.02223963376455413, 4.489604347827017, 0.013096190585963027], "isController": false}, {"data": ["019_GET_web/emazad/GetAuctionPrices/GetAsync", 12, 0, 0.0, 202.91666666666666, 191, 222, 204.0, 217.8, 222.0, 222.0, 0.02242081249287672, 0.02599339963977228, 0.036762250171425793], "isController": false}, {"data": ["001_GET_-1", 13, 0, 0.0, 6.384615384615384, 5, 7, 6.0, 7.0, 7.0, 7.0, 0.022240432764605546, 0.022978884633742844, 0.013031503573011066], "isController": false}, {"data": ["001_GET_-0", 13, 0, 0.0, 36.92307692307693, 9, 175, 20.0, 122.99999999999996, 175.0, 175.0, 0.02223898699703537, 0.09935875538226253, 0.01216194601400372], "isController": false}, {"data": ["002_GET_assets/appconfig.k8s.json", 13, 0, 0.0, 6.3076923076923075, 5, 7, 6.0, 7.0, 7.0, 7.0, 0.022240394715682215, 0.04209168453026575, 0.01018627453286617], "isController": false}, {"data": ["001_GET_", 13, 0, 0.0, 178.61538461538458, 149, 320, 165.0, 268.4, 320.0, 320.0, 0.022233395928894176, 21.43683675267998, 0.09062714317109795], "isController": false}, {"data": ["020_GET_web/emazad/GetLastFiveBiddings/GetAsync", 12, 0, 0.0, 251.74999999999997, 239, 262, 253.0, 260.8, 262.0, 262.0, 0.022419262630452085, 0.036704974414016524, 0.03682539037541055], "isController": false}, {"data": ["009_POST_web/emazad/OTP/SendByTempAccessToken", 12, 0, 0.0, 92.66666666666667, 88, 99, 92.0, 98.4, 99.0, 99.0, 0.02239177773921416, 0.009730801849560843, 0.01347005379624602], "isController": false}, {"data": ["010_POST_web/emazad/Account/VerifyOTPLogin", 12, 0, 0.0, 446.41666666666663, 385, 919, 396.5, 784.6000000000005, 919.0, 919.0, 0.022378498738412134, 0.08051014585186553, 0.013003131591167205], "isController": false}, {"data": ["024_POST_web/emazad/WalletOrders/CreateOrEdit", 12, 0, 0.0, 369.49999999999994, 337, 624, 346.5, 545.1000000000003, 624.0, 624.0, 0.022396667375894467, 0.009164261357909943, 0.036460199722281324], "isController": false}, {"data": ["026_POST_web/emazad/Bill/GetMyBills", 12, 0, 0.0, 430.4166666666667, 282, 1763, 308.5, 1340.9000000000015, 1763.0, 1763.0, 0.02240243738518751, 1.2803919108065624, 0.039532426127962726], "isController": false}, {"data": ["014_POST_web/emazad/GetCauseById/Execute", 12, 0, 0.0, 197.74999999999997, 189, 217, 197.0, 212.50000000000003, 217.0, 217.0, 0.02242060303948642, 0.029195318134344256, 0.037396865226018365], "isController": false}, {"data": ["003_GET_", 13, 0, 0.0, 6.0, 5, 7, 6.0, 7.0, 7.0, 7.0, 0.022240394715682215, 0.0054080647306688195, 0.014291191135662984], "isController": false}, {"data": ["023_POST_web/emazad/Bill/GetMyBills", 12, 0, 0.0, 429.75000000000006, 273, 1726, 282.5, 1363.9000000000015, 1726.0, 1726.0, 0.022407666409600936, 1.269654703695958, 0.039541653517723534], "isController": false}, {"data": ["015_POST_web/emazad/GetAuctionsByCauseId/List", 12, 0, 0.0, 204.5, 194, 219, 200.5, 218.4, 219.0, 219.0, 0.022420393590009472, 0.12281770456740786, 0.03927947861374707], "isController": false}, {"data": ["027_POST_webhook/handle-paid-event", 12, 0, 0.0, 115.33333333333333, 79, 210, 92.5, 203.10000000000002, 210.0, 210.0, 0.022414070058911648, 0.0023858726918177435, 0.016110112854842745], "isController": false}, {"data": ["012_POST_web/emazad/GetCausesOrAuctionsBySearch/Count", 12, 0, 0.0, 186.91666666666666, 165, 210, 186.5, 209.7, 210.0, 210.0, 0.0224036084745383, 0.01179252438259389, 0.041700466555146476], "isController": false}, {"data": ["033_POST_web/emazad/AddBid/AddBid", 12, 0, 0.0, 686.3333333333333, 624, 1058, 648.0, 949.4000000000003, 1058.0, 1058.0, 0.022392947714333165, 0.009403288590979747, 0.03705733982511108], "isController": false}, {"data": ["032_GET_web/emazad/GetAuctionPrices/GetAsync", 12, 0, 0.0, 202.83333333333331, 192, 222, 200.5, 220.8, 222.0, 222.0, 0.022411390962980116, 0.02598247686023883, 0.03674680217465197], "isController": false}, {"data": ["022_GET_web/emazad/GetMyWallet/GetAsync", 12, 0, 0.0, 154.5, 149, 160, 153.5, 160.0, 160.0, 160.0, 0.022423116738482927, 0.00935208929725952, 0.03486093930436017], "isController": false}]}, function(index, item){
        switch(index){
            // Errors pct
            case 3:
                item = item.toFixed(2) + '%';
                break;
            // Mean
            case 4:
            // Mean
            case 7:
            // Median
            case 8:
            // Percentile 1
            case 9:
            // Percentile 2
            case 10:
            // Percentile 3
            case 11:
            // Throughput
            case 12:
            // Kbytes/s
            case 13:
            // Sent Kbytes/s
                item = item.toFixed(2);
                break;
        }
        return item;
    }, [[0, 0]], 0, summaryTableHeader);

    // Create error table
    createTable($("#errorsTable"), {"supportsControllersDiscrimination": false, "titles": ["Type of error", "Number of errors", "% in errors", "% in all samples"], "items": []}, function(index, item){
        switch(index){
            case 2:
            case 3:
                item = item.toFixed(2) + '%';
                break;
        }
        return item;
    }, [[1, 1]]);

        // Create top5 errors by sampler
    createTable($("#top5ErrorsBySamplerTable"), {"supportsControllersDiscrimination": false, "overall": {"data": ["Total", 494, 0, "", "", "", "", "", "", "", "", "", ""], "isController": false}, "titles": ["Sample", "#Samples", "#Errors", "Error", "#Errors", "Error", "#Errors", "Error", "#Errors", "Error", "#Errors", "Error", "#Errors"], "items": [{"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}]}, function(index, item){
        return item;
    }, [[0, 0]], 0);

});
