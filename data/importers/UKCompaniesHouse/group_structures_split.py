import csv
import sys

ukcomp_fieldnames = ['version','gs002','regnum','safenum','name','holdnum','level','org','kfin','ultholdnum']
forcomp_fieldnames = ['version','gs002','regnum','safenum','name','holdnum','level','org','kfin','ultholdnum','country']

countrymap = {}

def split_foreign_companies():
    print "Splitting foreign companies...",
    sys.stdout.flush()

    groups = csv.reader(open('cs_uk_group_structure.csv', 'r'))
    groups.next() # skip header

    ukcomp = csv.writer(open("cs_uk_group_structure_ukcomp.csv", "w"))
    ukcomp.writerow(ukcomp_fieldnames)

    forcomp = csv.writer(open("cs_uk_group_structure_forcomp.csv", "w"))
    forcomp.writerow(forcomp_fieldnames)

    try:
        for comp in groups:
            comp.append("GeoNames")
            data = dict(zip(ukcomp_fieldnames, comp))
            if data["regnum"].lower().find("foreign") != -1:
                country = data["safenum"][:2].upper()
                if country == '':
                    if data["regnum"] not in countrymap:
                        countrymap[data["regnum"]] = raw_input('What country is "%s"?' % data["regnum"])
                    country = countrymap[data["regnum"]]
                comp.append(country)
                forcomp.writerow(comp)
            else:
                ukcomp.writerow(comp)

            # Show some status every now and then:
            if groups.line_num % 100 == 0:
                print "\rSplitting foreign companies... %d" % (groups.line_num),
                sys.stdout.flush()
    except Exception, e:
        print "CSV ERROR: ", e

    print "DONE"

if __name__ == "__main__":
    split_foreign_companies()