#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Sep 16 11:30:48 2021

The script contains the functions used in Sapelo2_extract_somatic_germline.py

@author: kun-linho
"""

import collections
import os
import re
import sys
from copy import copy
from pathlib import Path

import numpy as np
import pandas as pd


def extractVAF(gatk_info):
    if len(gatk_info.split(":")) > 1:
        vaf_info = gatk_info.split(":")[1].split(",")
        ref = int(vaf_info[0])
        alt = int(vaf_info[1])
        # vaf_value = float(alt/(ref+alt))
    else:
        ref = "No info provided"
        alt = "No info provided"

    return pd.Series([ref, alt])


## the function is same as df.explode but in case pandas version < 1.3
## there is a extra function
def unnesting(df, explode):
    idx = df.index.repeat(df[explode[0]].str.len())
    df1 = pd.concat(
        [pd.DataFrame({x: np.concatenate(df[x].values)}) for x in explode], axis=1
    )
    df1.index = idx

    return df1.join(df.drop(explode, 1), how="left")


## the function that use to extract the ensembl gene and ensembl transcripts given the annovar annotated results
## ex: 'ENSCAFG00000023363:ENSCAFT00000000040:exon7:c.762dupA:p.G255fs,' and it will return ENSCAFG0000023363, ENSCAFT0000000040, G255fs
## even we have multiple annotation, it will join them together with ','
def extractAnnovarMutProtein(mut_info):
    try:
        Ensembl_gene = re.findall(r"(ENSCAFG)(\d+):", mut_info)
        Ensembl_trans = re.findall(r"(ENSCAFT)(\d+):", mut_info)

        ## the overall regex for annovar
        total_protein_mut = re.findall(r"p.([A-Z0-9a-z_.*-]*),", mut_info)
        total_ensembl_gene = ["".join(i) for i in Ensembl_gene]
        Total_protein_change = ["".join(i) for i in total_protein_mut]
        total_trans = ["".join(i) for i in Ensembl_trans]
        diff = abs(len(Total_protein_change) != len(total_trans))
        # in case that the annovar ensemble transcripts and the protein changes are not the same length, I add "No_Info_Provided" until they are the same
        while diff != 0:
            if len(Total_protein_change) > len(total_trans):
                total_trans += ["No_Info_Provided"]
                total_ensembl_gene += ["No_Info_Provided"]
            elif len(Total_protein_change) < len(total_trans):
                Total_protein_change += ["No_Info_Provided"]

            diff = abs(len(Total_protein_change) != len(total_trans))

        # combine into a big string
        Total_ensembl_gene = ",".join(total_ensembl_gene)
        Total_protein_change = ",".join(Total_protein_change)
        total_trans = ",".join(total_trans)

        final_return = pd.Series(
            [Total_ensembl_gene, total_trans, Total_protein_change]
        )

        return final_return
    except:
        print("There is an error in sample " + sample_name)


def process_gatk_output(gatk_vcf):
    gatk_data = pd.read_csv(gatk_vcf, sep="\t", header=None)
    gatk_data.loc[:, "Line"] = ["line" + str(i + 1) for i in range(0, len(gatk_data))]
    gatk_data.loc[:, ["Ref_reads", "Alt_reads"]] = (
        gatk_data[9].astype(str).apply(extractVAF).to_numpy()
    )

    target_gatk = gatk_data.loc[:, [0, 3, 4, 9, 10, "Ref_reads", "Alt_reads", "Line"]]
    target_gatk.columns = [
        "Chrom",
        "Ref",
        "Alt",
        "VAF_info",
        "Sample_name",
        "Ref_reads",
        "Alt_reads",
        "Line",
    ]

    return target_gatk


## this function will process annovar output and extract all the protein changes in the annovar file (not only one protein change)
## it will remove Ensembl gene that located in retro_gene list idenitfied in pan-cancer paper
## even the annovar contains sample name, it will overwrite the orignal one
## the final return table contains the following
## Line','Consequence','Gene_name','Chrom','Start','End','Ref','Alt','Sample_name','Ensembl_gene','Ensembl_transcripts','Total_protein_change'
## the reason I keep line is for future used for VAF calculation
def processAnnovar(annovar_gene_file, retro_gene_file, sample_name):
    retro_gene_list = pd.read_csv(retro_gene_file, sep="\n", header=None)[0].tolist()
    annovar_gene_data = pd.read_csv(annovar_gene_file, sep="\t", header=None)
    # Define column names for Annovar gene data
    annovar_output_col = [
        "Line",
        "Consequence",
        "Annovar_info",
        "Chrom",
        "Start",
        "End",
        "Ref",
        "Alt",
        "Homo_hetro",
        "10",
        "11",
        "12",
        "13",
        "Gene_name",
        "Sample_name",
    ]
    annovar_gene_data.columns = annovar_output_col
    annovar_gene_data.loc[
        :, ["Ensembl_gene", "Ensembl_transcripts", "Total_protein_change"]
    ] = (annovar_gene_data["Annovar_info"].apply(extractAnnovarMutProtein).to_numpy())
    ## in case the Ensembl_transcripts and Total_protein_change are not in the same length,
    ## I add "No_Info_Provided" in the extractAnnovarMutProtein steps, so we need to exclude that information
    annovar_gene_data = annovar_gene_data.loc[
        (annovar_gene_data["Ensembl_transcripts"] != "No_Info_Provided")
        & (annovar_gene_data["Total_protein_change"] != "No_Info_Provided")
    ]
    target_annovar_info = annovar_gene_data.loc[
        :,
        [
            "Line",
            "Consequence",
            "Gene_name",
            "Chrom",
            "Start",
            "End",
            "Ref",
            "Alt",
            "Sample_name",
            "Ensembl_gene",
            "Ensembl_transcripts",
            "Total_protein_change",
        ],
    ]
    # Split multiple values in columns
    target_annovar_info["Gene_name"] = (
        target_annovar_info["Gene_name"].astype(str).str.split(",")
    )
    target_annovar_info["Ensembl_gene"] = (
        target_annovar_info["Ensembl_gene"].astype(str).str.split(",")
    )
    target_annovar_info["Ensembl_transcripts"] = (
        target_annovar_info["Ensembl_transcripts"].astype(str).str.split(",")
    )
    target_annovar_info["Total_protein_change"] = (
        target_annovar_info["Total_protein_change"].astype(str).str.split(",")
    )
    #### unnesting is the same as explode but just in case pandas version is < 1.3
    # target_annovar_info = unnesting(target_annovar_info,['Ensembl_transcripts','Total_protein_change'])
    target_annovar_info = target_annovar_info.explode(
        ["Gene_name", "Ensembl_gene", "Ensembl_transcripts", "Total_protein_change"]
    )
    # Exclude entries with "No_Info_Provided" again
    target_annovar_info = target_annovar_info[
        (target_annovar_info["Ensembl_transcripts"] != "No_Info_Provided")
        & (target_annovar_info["Total_protein_change"] != "No_Info_Provided")
    ]
    ### filter retrogene list with given ensembl id
    target_annovar_info = target_annovar_info[
        ~target_annovar_info.Ensembl_gene.isin(retro_gene_list)
    ]
    target_annovar_info.loc[:, "Gene_mut_info"] = (
        target_annovar_info["Gene_name"]
        + "_"
        + target_annovar_info["Total_protein_change"]
    )
    target_annovar_info.loc[:, "Transcript_mut_info"] = (
        target_annovar_info["Ensembl_transcripts"]
        + "_"
        + target_annovar_info["Total_protein_change"]
    )
    # Drop duplicate entries
    target_annovar_info = target_annovar_info.drop_duplicates()
    return target_annovar_info


def isNaN(num):
    return num != num


def convertEmptyGene(GeneName):
    if GeneName == "-" or GeneName == "-_WildType":
        GeneName = GeneName.replace("-", "NoGeneName")

    return GeneName


def createDictforHumanDogSearch(clean_translate_table):
    total_dict = {}
    #### create human_dog translation dict for future search
    human_dog_pos_dict = {}
    dog_human_pos_dict = {}
    human_aa_dict = {}
    dog_aa_dict = {}

    for entry in clean_translate_table:
        gene = entry[1]
        human_pos = entry[2]
        dog_pos = entry[3]
        human_aa = entry[4]
        dog_aa = entry[5]

        if gene not in human_dog_pos_dict:
            human_dog_pos_dict[gene] = {}
            dog_human_pos_dict[gene] = {}
            human_aa_dict[gene] = {}
            dog_aa_dict[gene] = {}

        human_dog_pos_dict[gene][human_pos] = dog_pos
        dog_human_pos_dict[gene][dog_pos] = human_pos
        human_aa_dict[gene][human_pos] = human_aa
        dog_aa_dict[gene][dog_pos] = dog_aa

    total_dict["human_dog_pos_dict"] = human_dog_pos_dict
    total_dict["dog_human_pos_dict"] = dog_human_pos_dict
    total_dict["human_aa_dict"] = human_aa_dict
    total_dict["dog_aa_dict"] = dog_aa_dict

    return total_dict


common_amino_acid_value = collections.OrderedDict(
    sorted(
        {
            "A": 0.05,
            "R": 0.05,
            "N": 0.05,
            "D": 0.05,
            "C": 0.05,
            "E": 0.05,
            "Q": 0.05,
            "G": 0.05,
            "H": 0.05,
            "I": 0.05,
            "L": 0.05,
            "K": 0.05,
            "M": 0.05,
            "F": 0.05,
            "P": 0.05,
            "S": 0.05,
            "T": 0.05,
            "W": 0.05,
            "Y": 0.05,
            "V": 0.05,
            "X": 0.05,
        }.items()
    )
)


## current function only care about SNV and fs, and these two is the only we can do the dog_human comparison
## the consequence results (fs,snv) are derived from annovar annotation results, other annotation might not work
# The following situations will have "No Counterparts"
#'Another species doesnt have the pos'
#'Current pos cannot align to another species'
#'Another species has no '+gene_name+' in the databases'
def identify_species_counterparts(
    gene_mut_info,
    human_dog_pos_dict,
    dog_human_pos_dict,
    human_aa_dict,
    dog_aa_dict,
    translate_to,
):
    gene_name, mut_info = gene_mut_info.split("_")

    if translate_to.upper() == "DOG":
        ref_dict, alt_dict = human_dog_pos_dict, dog_human_pos_dict
        other_species_aa_dict = dog_aa_dict
    else:
        ref_dict, alt_dict = dog_human_pos_dict, human_dog_pos_dict
        other_species_aa_dict = human_aa_dict

    pos = 0
    other_counterparts = "No Counterparts"

    if "fs" in mut_info:
        fs_info = re.search(r"([A-Za-z])(\d+)([A-Za-z]*)(fs)", mut_info)
        if fs_info:
            wt, pos, _, _ = fs_info.groups()
            situtation = "fs"
    ## SNV or stop gain
    elif re.search(r"([A-Za-z])(\d+)([A-Z])", mut_info):
        SNV_info = re.search(r"([A-Za-z])(\d+)([A-Z])", mut_info)
        if SNV_info:
            wt, pos, mut = SNV_info.groups()
            situtation = "SNV"

    if situtation:
        if gene_name in alt_dict:
            if (wt.upper() in common_amino_acid_value) and (
                mut.upper() in common_amino_acid_value
            ):
                if pos in ref_dict[gene_name]:
                    other_species_pos = ref_dict[gene_name][pos]
                    if other_species_pos in other_species_aa_dict[gene_name]:
                        other_species_wt = other_species_aa_dict[gene_name][
                            other_species_pos
                        ]
                        given_species_mut = mut
                        if wt == mut:
                            other_counterparts = (
                                gene_name
                                + "_"
                                + other_species_wt
                                + str(other_species_pos)
                                + other_species_wt
                            )
                        elif given_species_mut == other_species_wt:
                            other_counterparts = "No Mutation"
                        else:
                            if situtation == "SNV":
                                other_counterparts = (
                                    gene_name
                                    + "_"
                                    + other_species_wt
                                    + str(other_species_pos)
                                    + given_species_mut
                                )
                            elif situtation == "fs":
                                other_counterparts = (
                                    gene_name
                                    + "_"
                                    + other_species_wt
                                    + str(other_species_pos)
                                    + "fs"
                                )

    return other_counterparts


## this function will select the mutations that can be found in human somatic db from (C-bio, or cosmeic) after human-dog position translation
def extract_human_somatic(
    mutation_file,
    human_dog_alginemt_file,
    human_dog_transcript,
    target_merge_gatk_annovar,
    translate_to,
):
    mutation_data = pd.read_csv(mutation_file, sep="\t")
    all_mutation_list = set(mutation_data["Mut_type"])

    translate_allign_table = pd.read_csv(human_dog_alginemt_file, sep="\t")
    translate_allign_table.loc[
        translate_allign_table["QueryAA"] == "-", "QueryIdx"
    ] = "-"
    clean_translate_table = translate_allign_table[
        translate_allign_table["QueryIdx"] != "-"
    ]

    total_summary_dict = createDictforHumanDogSearch(clean_translate_table.to_records())

    target_merge_gatk_annovar["Human_counterpart"] = target_merge_gatk_annovar[
        "Gene_mut_info"
    ].apply(
        identify_species_counterparts,
        human_dog_pos_dict=total_summary_dict["human_dog_pos_dict"],
        dog_human_pos_dict=total_summary_dict["dog_human_pos_dict"],
        human_aa_dict=total_summary_dict["human_aa_dict"],
        dog_aa_dict=total_summary_dict["dog_aa_dict"],
        translate_to=translate_to,
    )

    human_dog_transcript_info = pd.read_csv(
        human_dog_transcript,
        sep="\t",
        header=None,
        names=["Gene_name", "Human_transcripts", "Dog_transcripts"],
    )

    transcript_match_target_annovar = target_merge_gatk_annovar.loc[
        target_merge_gatk_annovar["Ensembl_transcripts"].isin(
            human_dog_transcript_info["Dog_transcripts"]
        )
    ]

    pass_data = transcript_match_target_annovar.loc[
        transcript_match_target_annovar["Human_counterpart"].isin(all_mutation_list)
    ]
    pass_data = pass_data.drop(columns="Human_counterpart")

    return pass_data
